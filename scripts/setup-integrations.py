"""Install the pinned optional FPS reader; valid bundled assets work offline."""
import hashlib,json
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1];VERSION="2.3.1";NAME=f"PresentMon-{VERSION}-x64.exe";DIRECTORY=ROOT/"integrations/presentmon";TARGET=DIRECTORY/NAME;MANIFEST=DIRECTORY/"manifest.json"
def local_valid():
    try:
        m=json.loads(MANIFEST.read_text(encoding="utf-8"));return m.get("version")==VERSION and m.get("executable")==NAME and TARGET.is_file() and hashlib.sha256(TARGET.read_bytes()).hexdigest()==m.get("sha256")
    except (OSError,ValueError,TypeError):return False
if local_valid():print("PresentMon is already installed and locally verified; skipping network access.",flush=True);raise SystemExit(0)
DIRECTORY.mkdir(parents=True,exist_ok=True)
try:
    with httpx.Client(timeout=30,follow_redirects=True,trust_env=False) as client:
        release=client.get(f"https://api.github.com/repos/GameTechDev/PresentMon/releases/tags/v{VERSION}");release.raise_for_status();asset=next(a for a in release.json()["assets"] if a["name"]==NAME);expected=(asset.get("digest") or "").removeprefix("sha256:");response=client.get(asset["browser_download_url"]);response.raise_for_status()
        if len(response.content)!=asset["size"]:raise ValueError("PresentMon download size mismatch")
        actual=hashlib.sha256(response.content).hexdigest()
        if expected and actual!=expected:raise ValueError("PresentMon checksum mismatch")
        temporary=TARGET.with_suffix(".download");temporary.write_bytes(response.content);temporary.replace(TARGET)
        license_response=client.get(f"https://raw.githubusercontent.com/GameTechDev/PresentMon/v{VERSION}/LICENSE.txt");license_response.raise_for_status();(DIRECTORY/"LICENSE.txt").write_bytes(license_response.content);MANIFEST.write_text(json.dumps({"version":VERSION,"executable":NAME,"sha256":actual,"upstream_digest":asset.get("digest")},indent=2),encoding="utf-8")
    print("PresentMon installed and checksum verified.",flush=True)
except Exception as error:
    print(f"WARNING: optional PresentMon integration could not be installed: {error}",flush=True);print("Core STONIC installation can continue; Gaming FPS will report unavailable.",flush=True);raise SystemExit(0)
