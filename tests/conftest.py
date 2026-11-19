import os
import shutil
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = Path(tempfile.mkdtemp(prefix="aa-tests-"))

# Set the environment before the package is imported for the first time.
os.environ["AIRDROP_HOME"] = str(BASE / "home")
os.environ["VAULT_PASSWORD"] = "test-passphrase-not-secret"
os.environ["AA_MODE"] = "balanced"
os.environ["LLM_MOCK"] = "1"
os.environ["CAPTCHA_PROVIDER"] = ""
os.environ["BROWSER_HEADLESS"] = "1"

import sys  # noqa: E402

sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def home(tmp_path):
    from aa import config, db

    for d in (config.HOME, config.DATA_DIR, config.VAULT_DIR, config.QUEST_DIR,
              config.PROOF_DIR, config.PROFILE_DIR, config.EXT_DIR):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
    os.chmod(config.HOME, 0o700)
    db.reset()
    config.ENV_FILE.write_text((config.CONFIG_DIR / "env.example").read_text())
    os.chmod(config.ENV_FILE, 0o600)
    config.KILL_FILE.unlink(missing_ok=True)
    yield config


@pytest.fixture
def vault():
    from aa import vault

    return vault


@pytest.fixture
def ident():
    from aa import db
    from aa.wallet import evm, hd, sol

    i = db.create_identity("tester", "casual-id")
    hd.ensure(i["id"])
    evm.derive(i["id"], 2)
    sol.derive(i["id"], 1)
    return i["id"]
