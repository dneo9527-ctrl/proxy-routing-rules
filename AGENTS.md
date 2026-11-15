# Routing Rules Maintenance

This repository is public. Store domain rules only; never add credentials, node
configs, subscription links, local authentication helpers, or private logs.

Canonical source: rules/{direct,proxy,residential,reject}.list. Only DOMAIN and
DOMAIN-SUFFIX, without policy suffixes. Preserve management/DNS/LAN precedence
in client configs and apply custom lists before broad base lists. Order:
reject > direct > residential > proxy. Residential must not fall back to DIRECT.

On an authorized change: edit source, run python3 scripts/rules.py build,
python3 scripts/rules.py check, and python3 -m unittest discover -s tests -v.
Commit and push before publishing the same revision through the local project's
existing 1Panel publishing helper. Recheck remote baseline before writing,
read back content, record commit SHA and hashes outside this public repository,
and verify client routing when available. Never install a background publisher
or reopen private node subscriptions for a rule-only edit.

GitHub CI validates only; it does not publish to the VPS. A direct GitHub edit
needs an explicit publishing step. Do not claim all clients were tested.
QX artifacts are generated and require client-side policy mapping.
