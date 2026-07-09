import os, pathlib

env_path = pathlib.Path.home() / '.hermes' / '.env'
for line in env_path.read_text(encoding='utf-8').splitlines():
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ[k.strip()] = v.strip()
os.environ['HERMES_HOME'] = str(pathlib.Path.home() / '.hermes')

from hermes_cli.model_switch import list_providers_with_models
results = list_providers_with_models()
for r in results:
    slug = r.get('slug', '')
    if slug.startswith('aide') or slug == 'claude-enterprise':
        print(f"{slug}: {r.get('total_models', 0)} models (source={r.get('source','?')})")
