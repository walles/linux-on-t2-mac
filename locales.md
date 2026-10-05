# Locales

Goal: make `Generating locales (this might take a while)...` faster. Every libc
or `locales` upgrade regenerates all locales, which took a while with the 66
the installer had set up.

## Why there were so many

The Ubuntu installer installs language packs for the eight most common
languages (de, en, es, fr, it, pt, ru, zh-hans) on top of the chosen one (sv).
Each `language-pack-XX-base` ships `/var/lib/locales/supported.d/XX`, listing
every country variant of that language, and `locale-gen` generates everything
in `supported.d/*` plus `/etc/locale.gen`.

## Setup

Remove the language packs for unused languages. Their removal scripts also
delete their compiled locales. Done 2026-10-05, freed 158 MB.

```
sudo apt purge '?name("^language-pack-(gnome-)?(de|es|fr|it|pt|ru|zh-hans)(-base)?$")'
```

The regex has to be in double quotes, otherwise apt's pattern parser chokes on
its parentheses.

What's left is `C`, `C.utf8`, `POSIX`, `sv_FI`, `sv_SE` and 23 English
variants. Check with `locale -a`.

## Not done: trimming English and Swedish further

Getting down to only `en_US`, `en_GB` and `sv_SE` would mean replacing the
lists in `supported.d/en` and `supported.d/sv`. Those belong to
`language-pack-en-base` and `language-pack-sv-base`, so plain edits get
overwritten on the next language pack update, and they would have to be moved
away with `dpkg-divert` instead. A dpkg `path-exclude` would backfire: the
language packs' install script runs `locale-gen --keep-existing en`, and with
`supported.d/en` missing, `locale-gen` falls back to enabling every English
variant in `/etc/locale.gen`.

Skipped, boring stock config wins over a slightly faster `locale-gen`.
