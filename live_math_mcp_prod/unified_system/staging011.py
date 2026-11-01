"""Owner CLI for the existing unified private staging application and model pipe."""
import argparse
import os
from pathlib import Path
import resource

from semantic_repair.inference011 import SubscriptionInference
from unified_system.staging009 import create_app


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('data', 'layer', 'cert', 'key', 'password', 'inference-spool'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--origin', required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--model', default='gpt-6.1-sol')
    options = parser.parse_args()
    os.umask(0o077)
    if not options.data.resolve().is_relative_to(Path.home()/'.local/state/livingmath'):
        raise ValueError('PRIVATE_STAGING_DATA_REQUIRED')
    # Start the model subprocess before Landlock. The app never reads model
    # credentials, nor grants its formal workers any new IO capability.
    provider = SubscriptionInference(options.inference_spool, model=options.model)
    try:
        app = create_app(options.data.resolve(), options.layer.resolve(), options.origin,
            options.password.read_text().strip(), deployment_id='general011-private-staging',
            semantic_provider=provider)
        import uvicorn
        resource.setrlimit(resource.RLIMIT_AS, (1073741824, 1073741824))
        uvicorn.run(app, host='127.0.0.1', port=options.port, ssl_certfile=str(options.cert),
            ssl_keyfile=str(options.key), access_log=False, proxy_headers=False, limit_concurrency=32)
    finally:
        provider.close()
