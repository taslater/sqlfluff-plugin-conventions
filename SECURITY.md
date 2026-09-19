# Security policy

## Supported versions

While the plugin is pre-1.0, only the latest release receives fixes.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting on this repository
(Security → Report a vulnerability) at
https://github.com/taslater/sqlfluff-plugin-conventions/security/advisories/new
Please do not open a public issue for anything security-related.

## Trust model

This plugin executes Python code in two ways, both deliberately:

- **SQLFluff plugins in general** are arbitrary Python. Installing this
  package and running SQLFluff means running its code, as with any plugin.
- **Comment scorers** are functions named in configuration: an entry-point
  name, a `module:function`, or a `path/to/scorer.py:function`. The code must
  already exist on the machine; nothing is fetched or `eval`'d from a string.
  A `.sqlfluff` file can therefore name a script to import, so treat config
  as code.

For shared or hardened CI, set `SQLFLUFF_CONVENTIONS_NO_FILE_SCORERS=1` to
refuse the file-path spelling and allow only installed modules and entry
points.
