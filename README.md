# ximing/grok-plugins

Grok Build marketplace for plugins maintained by [ximing](https://github.com/ximing).

Skills are **vendored** here from their source repositories. You do not edit files under `plugins/` by hand — a pipeline copies them whenever the upstream repo changes.

| Plugin | Upstream | Skills |
| --- | --- | --- |
| `rab` | [ximing/rab](https://github.com/ximing/rab) | `rab-react`, `rab-cdp-debug`, `rab-rn-debug` |
| `csi` | [ximing/csi](https://github.com/ximing/csi) | `csi`, `csi-e2e` |

## Install

```bash
grok plugin marketplace add ximing/grok-plugins
grok plugin install rab --trust
grok plugin install csi --trust
```

Or pin it in `~/.grok/config.toml`:

```toml
[[marketplace.sources]]
name = "ximing"
git = "https://github.com/ximing/grok-plugins.git"

[plugins]
enabled = ["rab", "csi"]
```

Then `grok plugin marketplace update` / `grok plugin update` picks up new skill copies.

## How sync works

```
ximing/rab  --skills change-->  GitHub Action  --deploy key-->  this repo
ximing/csi  --skills change-->  GitHub Action  --deploy key-->  this repo
this repo   --every 30 min--->  scripts/sync.py clones upstreams (safety net)
```

1. `sources.json` lists each plugin and its GitHub repo. **This is the only file you edit to add a plugin.**
2. `scripts/sync.py` clones (or uses a local checkout), copies `skills/`, `plugin.json`, and `LICENSE` into `plugins/<name>/`, and regenerates `.grok-plugin/marketplace.json` plus `.grok-plugin/plugin-index.json`.
3. Upstream repos run `.github/workflows/sync-grok-plugins.yml` on `skills/**` pushes. That workflow checks this repo out with a write deploy key and runs `sync.py --from-local`.
4. `.github/workflows/sync.yml` in this repo also runs every 30 minutes, so a missed notify still lands.

`plugins/<name>/SOURCE.json` records the upstream commit that was copied.

## Add another plugin

1. Append an entry to `sources.json` (`name`, `repo`, `ref`, `keywords`, …).
2. Copy `examples/sync-from-source.yml` into the upstream repo as `.github/workflows/sync-grok-plugins.yml`.
3. On the upstream repo, set secret `GROK_PLUGINS_DEPLOY_KEY` (write deploy key for this repo) and set `PLUGIN_NAME` in the copied workflow.
4. Push. The next skill change (or a `workflow_dispatch`) vendors it.

Local dry-run from this checkout:

```bash
python3 scripts/sync.py --local-map rab=~/project/mygithub/rab,csi=~/project/mygithub/csi
python3 scripts/validate.py
```

## Layout

```
sources.json                 # registry — edit this
scripts/sync.py              # copy + regenerate catalogs
scripts/validate.py
.grok-plugin/marketplace.json
.grok-plugin/plugin-index.json
plugins/rab/                 # generated
plugins/csi/                 # generated
```

Vendored plugin payloads keep their upstream license (`plugins/rab` is MIT, `plugins/csi` is PolyForm Noncommercial). The scaffolding in this repository is MIT.
