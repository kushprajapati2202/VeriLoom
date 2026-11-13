"""Live Cloud Deployment Verification Script for VeriLoom on Vercel."""

import sys
import time
import httpx

LIVE_URL = "https://veri-loom-kushprajapati2202s-projects.vercel.app"


def test_step(step_name: str, check_fn) -> bool:
    print(f"[*] Testing: {step_name}...", end=" ", flush=True)
    try:
        t0 = time.time()
        success, details = check_fn()
        elapsed = int((time.time() - t0) * 1000)
        if success:
            print(f"[PASS] ({elapsed}ms) - {details}")
            return True
        else:
            print(f"[FAIL] - {details}")
            return False
    except Exception as e:
        print(f"[ERROR: {e}]")
        return False


def main():
    print("==========================================================")
    print("  VeriLoom Live Cloud Deployment Test Suite (Vercel)      ")
    print(f"  Target: {LIVE_URL} ")
    print("==========================================================")

    client = httpx.Client(base_url=LIVE_URL, timeout=15.0, follow_redirects=True)
    all_passed = True

    # 1. Root Dashboard
    def check_root():
        r = client.get("/")
        return r.status_code == 200 and "VeriLoom" in r.text, f"HTTP {r.status_code}, HTML length {len(r.text)}"

    # 2. Dashboard alias
    def check_dashboard():
        r = client.get("/dashboard")
        return r.status_code == 200 and "VeriLoom" in r.text, f"HTTP {r.status_code}, Title verified"

    # 2b. Index.html alias
    def check_index_html():
        r = client.get("/index.html")
        return r.status_code == 200 and "VeriLoom" in r.text, f"HTTP {r.status_code}, HTML length {len(r.text)}"

    # 2c. Favicon.ico clean handling
    def check_favicon():
        r = client.get("/favicon.ico")
        return r.status_code in (200, 204), f"HTTP {r.status_code} (Clean icon response)"

    # 3. Swagger Docs
    def check_docs():
        r = client.get("/docs")
        return r.status_code == 200, f"HTTP {r.status_code}, OpenAPI Interactive UI ready"

    # 4. Status API
    def check_status():
        r = client.get("/api/status")
        data = r.json()
        return r.status_code == 200 and data.get("status") == "online", f"Status: {data.get('status')}, Service: {data.get('service')}"

    # 5. Repository Inspect API (POST)
    def check_inspect():
        r = client.post("/api/repository/inspect", json={"repo_path": "."})
        data = r.json()
        sha = data.get("repository", {}).get("starting_commit", "")
        pts = len(data.get("capability_map", {}).get("candidate_extension_points", []))
        return r.status_code == 200 and len(sha) >= 10, f"HTTP 200, SHA: {sha[:10]}..., Extension Points: {pts}"

    # 6. Packages List API (GET)
    def check_packages():
        r = client.get("/api/packages")
        data = r.json()
        pkgs = data.get("packages", [])
        return r.status_code == 200 and isinstance(pkgs, list), f"HTTP 200, Exported Packages: {len(pkgs)}"

    # 7. Invalid package error handling (404)
    def check_benchmark_404():
        r = client.post(
            "/api/benchmark/evaluate",
            json={
                "package_dir": "non_existent_pkg_xyz_404",
                "solution_code": "def foo(): pass",
                "model_name": "live-tester",
            },
        )
        return r.status_code == 404, f"HTTP {r.status_code} (Graceful error handling verified)"

    checks = [
        ("Web Engineering Dashboard (GET /)", check_root),
        ("Dashboard Route Alias (GET /dashboard)", check_dashboard),
        ("Index.html Direct URL (GET /index.html)", check_index_html),
        ("Favicon Handler (GET /favicon.ico)", check_favicon),
        ("Interactive OpenAPI Docs (GET /docs)", check_docs),
        ("Service Health API (GET /api/status)", check_status),
        ("Repository Intelligence Inspect (POST /api/repository/inspect)", check_inspect),
        ("Task Package Catalog API (GET /api/packages)", check_packages),
        ("Defensive Benchmark Error Handling (POST 404 check)", check_benchmark_404),
    ]

    for name, fn in checks:
        if not test_step(name, fn):
            all_passed = False

    print("==========================================================")
    if all_passed:
        print("  ALL LIVE CLOUD TESTS PASSED! VERCEL DEPLOYMENT 100% OPERATIONAL! ")
    else:
        print("  SOME CHECKS FAILED - REVIEW OUTPUT ABOVE.               ")
    print("==========================================================")
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()

