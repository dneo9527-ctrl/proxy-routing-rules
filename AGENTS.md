# Routing Rules Maintenance

This repository is public. Store domain rules only; never add credentials, node
configs, subscription links, local authentication helpers, or private logs.

Canonical source: rules/{direct,proxy,residential,reject}.list. Only DOMAIN and
DOMAIN-SUFFIX, without policy suffixes. Preserve management/DNS/LAN precedence
in client configs and apply custom lists before broad base lists. Order:
reject > direct > residential > proxy. Residential must not fall back to DIRECT.

On an authorized change: edit source, run python3 scripts/rules.py build,
python3 scripts/rules.py check, and python3 -m unittest discover -s tests -v.
Commit and push to main. A green GitHub Actions run creates the validated
release branch; the visible 1Panel task pulls that branch with the pinned
kubernetes/git-sync image and runs the separately installed fixed publisher.
The publisher validates the manifest, CI provenance, and all cross-list rules
before switching the public directory. Recheck the published SHA and hashes,
and verify client routing when available. Never execute code from a downloaded
checkout, reopen private node subscriptions, or add an untracked background
publisher for a rule-only edit.

GitHub Actions publishes only the validated release branch; the VPS task
publishes that branch to the existing public directory. Direct edits on main
therefore wait for CI and the next visible task run. Do not claim all clients
were tested.
QX artifacts are generated and require client-side policy mapping.
