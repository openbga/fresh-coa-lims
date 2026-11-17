from playwright.sync_api._generated import Locator
from test_stability_testing_journey import *  # noqa: F401,F403 (fixtures)
import test_stability_testing_journey as j

_bb = Locator.bounding_box

def bb(self, *a, **k):
    box = _bb(self, *a, **k)
    if box and box["x"] + box["width"] > 390:
        print("PROBE", self.evaluate("e => e.outerHTML.slice(0, 300) + ' || parent: ' + e.parentElement.outerHTML.slice(0, 400)"))
    return box

Locator.bounding_box = bb
test_probe = j.test_stability_pull_is_tested_in_the_system_and_the_lot_record_is_left_alone
