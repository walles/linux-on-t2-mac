import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';

import * as Main from '../ui/main.js';
import * as SignalTracker from '../misc/signalTracker.js';

const SCALE_N_STEPS = 20;
const BRIGHTNESS_ANIM_INTERVAL_MS = 16;
const BRIGHTNESS_ANIM_THRESHOLD = 0.002;
const BRIGHTNESS_SMOOTHING_USER = 0.3;
const BRIGHTNESS_SMOOTHING_DIMMING = 0.05;
const BRIGHTNESS_SMOOTHING_AUTO = 0.08;

const KEYBINDING_SCHEMA = 'org.gnome.shell.keybindings';
const POWER_SCHEMA = 'org.gnome.settings-daemon.plugins.power';

class MonitorId {
    constructor(options) {
        this._vendor = options.vendor;
        this._product = options.product;
        this._serial = options.serial;
        this._colorMode = options.colorMode;
        this._connector = options.connector;
    }

    static fromMonitor(logicalMonitor) {
        const monitor = logicalMonitor.get_monitors()[0];
        return new MonitorId({
            vendor: monitor.get_vendor(),
            product: monitor.get_product(),
            serial: monitor.get_serial(),
            colorMode: monitor.get_color_mode_string?.() ?? 'default', // not in mutter 50.1
            connector: monitor.get_connector(),
        });
    }

    // Connector is excluded so a monitor moved to a different port
    // still matches its saved brightness
    equals(other) {
        return this._vendor === other._vendor &&
               this._product === other._product &&
               this._serial === other._serial &&
               this._colorMode === other._colorMode;
    }

    equalsExact(other) {
        return this.equals(other) &&
               this._connector === other._connector;
    }

    toTuple() {
        return [
            this._vendor,
            this._product,
            this._serial,
            this._colorMode,
            this._connector,
        ];
    }

    static fromTuple(tuple) {
        return new MonitorId({
            vendor: tuple[0],
            product: tuple[1],
            serial: tuple[2],
            colorMode: tuple[3],
            connector: tuple[4],
        });
    }
}

export const BrightnessManager = GObject.registerClass({
    Signals: {
        'changed': {},
        'user-update': {},
    },
}, class BrightnessManager extends GObject.Object {
    constructor() {
        super();

        this._globalScale = null;
        this._globalScaleNotifyId = 0;
        this._monitorScales = new Map();
        this._updating = false;
        this._saveBrightnessId = 0;

        // The power plugin uses idle-brightness for the keyboard backlight
        // too, so reuse that setting as the dimming target here
        const powerSettings = new Gio.Settings({schema_id: POWER_SCHEMA});
        this._dimmingTarget = powerSettings.get_int('idle-brightness') / 100;
        this._dimmingEnabled = false;
        this._abTarget = -1.0;

        this._setupKeybindings();

        const monitorManager = global.backend.get_monitor_manager();
        monitorManager.connectObject('monitors-changed',
            () => this._onMonitorsChanged(), this);
        this._onMonitorsChanged();
    }

    get dimming() {
        return this._dimmingEnabled;
    }

    set dimming(enable) {
        if (this._dimmingEnabled === enable)
            return;
        this._dimmingEnabled = enable;
        this._applyToBacklights({smoothing: BRIGHTNESS_SMOOTHING_DIMMING});
    }

    get autoBrightnessTarget() {
        return this._abTarget;
    }

    set autoBrightnessTarget(target) {
        if (this._abTarget === target)
            return;
        this._abTarget = target;
        this._applyToBacklights({smoothing: BRIGHTNESS_SMOOTHING_AUTO});
    }

    get globalScale() {
        return this._globalScale;
    }

    get scales() {
        return [...this._monitorScales.values()];
    }

    _setupKeybindings() {
        const settings = new Gio.Settings({schema_id: KEYBINDING_SCHEMA});

        // Unlike volume keys which are held down and use software key
        // repeat, brightness keys generate discrete press+release pairs
        // from firmware/ACPI, making software key repeat impossible.
        const bindings = [
            ['screen-brightness-up', () => this._globalScale?.stepUp()],
            ['screen-brightness-up-monitor', () => this._currentMonitorScale()?.stepUp()],
            ['screen-brightness-down', () => this._globalScale?.stepDown()],
            ['screen-brightness-down-monitor', () => this._currentMonitorScale()?.stepDown()],
            ['screen-brightness-cycle', () => this._globalScale?.cycleUp()],
            ['screen-brightness-cycle-monitor', () => this._currentMonitorScale()?.cycleUp()],
        ];

        for (const [name, handler] of bindings) {
            Main.wm.addKeybinding(name, settings,
                Meta.KeyBindingFlags.NONE, Shell.ActionMode.ALL,
                () => handler());
        }
    }

    _currentMonitorScale() {
        const monitor = global.backend.get_current_logical_monitor();
        return this._monitorScales.get(monitor);
    }

    _onMonitorsChanged() {
        this._updating = true;

        this._monitorScales.values().forEach(scale => scale.destroy());
        this._monitorScales.clear();

        const monitors = global.backend
            .get_monitor_manager()
            .get_logical_monitors()
            .filter(lm => {
                return lm.get_monitors()
                    .some(m => m.get_backlight() && m.is_active());
            });
        const savedBrightnesses = this._getSavedBrightnesses(monitors);

        for (const monitor of monitors) {
            const scale = new MonitorBrightnessScale(monitor);
            const saved = savedBrightnesses.get(monitor);

            if (saved >= 0)
                scale.value = saved;
            else
                scale.readFromBacklight();

            scale.connectObject(
                'backlight-changed', () => this._onBacklightChanged(scale),
                'notify::value', () => this._onMonitorScaleChanged(scale),
                this);

            this._monitorScales.set(monitor, scale);
        }

        if (this._globalScale) {
            this._globalScale.disconnect(this._globalScaleNotifyId);
            this._globalScale = null;
            this._globalScaleNotifyId = 0;
        }

        if (monitors.length > 0) {
            // Cap the step count so key-based adjustment stays usable
            // even when hardware supports many fine-grained steps
            const maxSteps = Math.max(
                ...[...this._monitorScales.values()].map(s => s.nSteps));
            const nSteps = Math.min(maxSteps, SCALE_N_STEPS);

            this._globalScale = new BrightnessScale(_('Brightness'), 1.0, nSteps);
            this._globalScaleNotifyId = this._globalScale.connect(
                'notify::value', () => this._onGlobalScaleChanged());
        }

        this._syncGlobalFromMonitors();
        this._applyToBacklights();
        this._saveBrightnesses();

        this._updating = false;
        this.emit('changed');
    }

    _onBacklightChanged(scale) {
        if (this._updating)
            return;

        this._updating = true;

        scale.stopAnimation();
        scale.readFromBacklight();
        // Disable dimming on any system-initiated backlight change
        this._dimmingEnabled = false;
        this._syncGlobalFromMonitors();
        this._applyToBacklights();
        this._saveBrightnesses();

        this._updating = false;
    }

    _onMonitorScaleChanged(scale) {
        if (this._updating)
            return;

        this._updating = true;

        this._syncGlobalFromMonitors();
        this._applyToBacklights({smoothing: BRIGHTNESS_SMOOTHING_USER});
        this._saveBrightnesses();
        this._showOSD([scale]);

        this._updating = false;
        this.emit('user-update');
    }

    _onGlobalScaleChanged() {
        if (this._updating)
            return;

        this._updating = true;

        for (const scale of this._monitorScales.values())
            scale.value = this._globalScale.value * scale.scaleFactor;

        this._applyToBacklights({smoothing: BRIGHTNESS_SMOOTHING_USER});
        this._saveBrightnesses();
        this._showOSD(this._monitorScales.values());

        this._updating = false;
        this.emit('user-update');
    }

    _syncGlobalFromMonitors() {
        if (!this._globalScale)
            return;

        // The global scale tracks the maximum of all monitor scales. Each
        // monitor's scaleFactor records its ratio to the maximum, so that
        // adjusting the global scale preserves the relative brightness
        // between monitors.
        const max = Math.max(
            ...[...this._monitorScales.values()].map(s => s.value));

        // Near zero we can't deduce meaningful ratios
        if (max > 0.01) {
            for (const scale of this._monitorScales.values())
                scale.scaleFactor = scale.value / max;
        }

        this._globalScale.value = max;
    }

    _applyToBacklights({smoothing = 0} = {}) {
        for (const scale of this._monitorScales.values()) {
            // When auto-brightness is active, the scale acts as a bias
            // around the sensor target rather than an absolute brightness
            const target = this._abTarget >= 0.0
                ? Math.clamp(this._abTarget + scale.value - 0.5, 0.0, 1.0)
                : scale.value;
            const max = this._dimmingEnabled ? this._dimmingTarget : 1.0;
            const brightness = Math.min(max, target);

            if (smoothing > 0)
                scale.animateToBacklight(brightness, smoothing);
            else
                scale.writeToBacklight(brightness);
        }
    }

    _getState() {
        return global.get_persistent_state('a(sssssd)', 'brightnesses')
            ?.deepUnpack().map(tuple => {
                const brightness = tuple.pop();
                return {id: MonitorId.fromTuple(tuple), brightness};
            }) ?? [];
    }

    _setState(values) {
        const tuple = new GLib.Variant('a(sssssd)', [...values].map(value => {
            const {id, brightness} = value;
            return [...id.toTuple(), brightness];
        }));
        global.set_persistent_state('brightnesses', tuple);
    }

    _getSavedBrightnesses(monitors) {
        const map = new Map();
        const saved = this._getState();

        for (const logicalMonitor of monitors) {
            const mId = MonitorId.fromMonitor(logicalMonitor);
            const {brightness} = saved.find(s => s.id.equalsExact(mId)) ??
                saved.find(s => s.id.equals(mId)) ??
                {brightness: -1.0};

            map.set(logicalMonitor, brightness);
        }

        return map;
    }

    _saveBrightnesses() {
        if (this._saveBrightnessId) {
            GLib.source_remove(this._saveBrightnessId);
            this._saveBrightnessId = 0;
        }

        this._saveBrightnessId = GLib.timeout_add_once(
            GLib.PRIORITY_DEFAULT, 300, () => {
                this._saveBrightnessId = 0;

                let values = this._getState();

                for (const scale of this._monitorScales.values()) {
                    const mId = MonitorId.fromMonitor(scale.monitor);
                    values = values.filter(v => !v.id.equalsExact(mId));
                    values.push({id: mId, brightness: scale.value});
                }

                this._setState(values);
            });
    }

    _showOSD(monitorScales) {
        const osdMonitors = {};
        for (const scale of monitorScales) {
            const level = scale.value;
            osdMonitors[scale.monitor.get_number()] = {level};
        }

        Main.osdWindowManager.show(
            Gio.Icon.new_for_string('display-brightness-symbolic'),
            null,
            osdMonitors
        );
    }
});

export const BrightnessScale = GObject.registerClass({
    Properties: {
        'value': GObject.ParamSpec.float(
            'value', null, null,
            GObject.ParamFlags.READWRITE,
            0, 1.0, 1.0),
    },
    Signals: {
        'destroy': {},
    },
}, class BrightnessScale extends GObject.Object {
    constructor(name, value = 1.0, nSteps = SCALE_N_STEPS) {
        super();

        this._name = name;
        this._value = value;
        this._nSteps = nSteps;
    }

    get name() {
        return this._name;
    }

    get value() {
        return this._value;
    }

    set value(value) {
        value = Math.clamp(value, 0.0, 1.0);
        if (this._value === value)
            return;
        this._value = value;
        this.notify('value');
    }

    get nSteps() {
        return this._nSteps;
    }

    stepUp() {
        this.value = this._value + (1.0 / this._nSteps);
    }

    stepDown() {
        this.value = this._value - (1.0 / this._nSteps);
    }

    cycleUp() {
        if (this._value >= 1.0)
            this.value = 0.0;
        else
            this.stepUp();
    }

    destroy() {
        this.emit('destroy');
    }
});
SignalTracker.registerDestroyableType(BrightnessScale);

const MonitorBrightnessScale = GObject.registerClass({
    Signals: {
        'backlight-changed': {},
    },
}, class MonitorBrightnessScale extends BrightnessScale {
    constructor(monitor) {
        const name = monitor.get_monitors()[0].get_display_name();

        // Cap step count for backlights with many fine-grained steps
        const maxSteps = Math.max(...monitor.get_monitors()
            .filter(m => m.get_backlight() && m.is_active())
            .map(m => {
                const b = m.get_backlight();
                return b.brightnessMax - b.brightnessMin;
            }));
        const nSteps = Math.min(maxSteps, SCALE_N_STEPS);

        super(name, 1.0, nSteps);

        this._monitor = monitor;
        this._scaleFactor = 1.0;
        this._writingBacklight = false;
        this._animId = 0;
        this._animTarget = 0;
        this._animCurrent = 0;

        this._backlights = this._monitor.get_monitors()
            .filter(m => m.get_backlight() && m.is_active())
            .map(m => m.get_backlight());

        for (const backlight of this._backlights) {
            backlight.connectObject('notify::brightness', () => {
                if (!this._writingBacklight)
                    this.emit('backlight-changed');
            }, this);
        }
    }

    destroy() {
        this.stopAnimation();
        super.destroy();
    }

    get monitor() {
        return this._monitor;
    }

    get scaleFactor() {
        return this._scaleFactor;
    }

    set scaleFactor(factor) {
        this._scaleFactor = factor;
    }

    _getBacklights() {
        return this._backlights;
    }

    _getCurrentRelativeBrightness() {
        const [backlight] = this._getBacklights();
        if (!backlight)
            return -1;

        const {brightness, brightnessMin: min, brightnessMax: max} = backlight;
        if (max <= min)
            return -1;

        return (brightness - min) / (max - min);
    }

    readFromBacklight() {
        const rel = this._getCurrentRelativeBrightness();
        if (rel >= 0)
            this.value = rel;
    }

    writeToBacklight(brightness) {
        this.stopAnimation();
        this._writeRaw(brightness);
    }

    animateToBacklight(brightness, smoothing) {
        this._animTarget = brightness;
        this._animSmoothing = smoothing;

        // Already animating. The running timer picks up the new target and
        // smoothing on its next tick.
        if (this._animId)
            return;

        const current = this._getCurrentRelativeBrightness();
        this._animCurrent = current >= 0 ? current : brightness;

        this._animId = GLib.timeout_add(
            GLib.PRIORITY_DEFAULT, BRIGHTNESS_ANIM_INTERVAL_MS, () => {
                return this._animTick();
            });
    }

    stopAnimation() {
        if (this._animId) {
            GLib.source_remove(this._animId);
            this._animId = 0;
        }
    }

    _animTick() {
        const diff = this._animTarget - this._animCurrent;

        if (Math.abs(diff) < BRIGHTNESS_ANIM_THRESHOLD) {
            this._writeRaw(this._animTarget);
            this._animId = 0;
            return GLib.SOURCE_REMOVE;
        }

        this._animCurrent += diff * this._animSmoothing;
        this._writeRaw(this._animCurrent);
        return GLib.SOURCE_CONTINUE;
    }

    _writeRaw(brightness) {
        this._writingBacklight = true;
        for (const backlight of this._getBacklights()) {
            const {brightnessMin: min, brightnessMax: max} = backlight;
            backlight.brightness = min + ((max - min) * brightness);
        }
        this._writingBacklight = false;
    }
});
