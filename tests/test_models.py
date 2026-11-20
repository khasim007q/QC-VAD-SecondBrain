import sys
import threading
import time

from classnotes import models


def test_kill_active_stops_a_running_conversion():
    result = {}

    def run():
        result["code"] = models.run_tracked(
            [sys.executable, "-c", "import time; time.sleep(60)"]).returncode

    t = threading.Thread(target=run)
    t.start()
    t0 = time.time()
    while not models._active and time.time() - t0 < 10:
        time.sleep(0.05)
    models.kill_active()
    t.join(10)
    assert not t.is_alive()
    assert result["code"] != 0
