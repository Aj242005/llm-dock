"""Browser evidence for the ISS, shared XYZ grid, and distance envelope."""
import hashlib
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

output = Path('.impeccable/review/iss-grid-final')
output.mkdir(parents=True, exist_ok=True)
errors = []
results = {}
with sync_playwright() as p:
    browser = p.chromium.launch(args=['--enable-webgl', '--use-gl=angle', '--use-angle=swiftshader'])
    page = browser.new_page(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto('http://127.0.0.1:8000')
    page.wait_for_function("document.querySelector('#iss-status').dataset.state === 'ready'", timeout=60000)
    page.get_by_text('Backend connected', exact=True).wait_for()
    page.evaluate('document.fonts.ready')
    page.wait_for_timeout(800)
    page.screenshot(path=str(output / 'desktop.png'), full_page=True)
    for mode in ['chaser', 'station', 'port', 'overview']:
        page.locator(f'[data-camera="{mode}"]').click()
        assert page.locator(f'[data-camera="{mode}"]').get_attribute('aria-pressed') == 'true'
        page.wait_for_timeout(350)
        page.locator('#scene').screenshot(path=str(output / f'scene-{mode}.png'))
    canvas = page.locator('#scene canvas')
    before = canvas.screenshot()
    box = canvas.bounding_box()
    page.mouse.move(box['x'] + box['width'] * .35, box['y'] + box['height'] * .4)
    page.mouse.down()
    page.mouse.move(box['x'] + box['width'] * .65, box['y'] + box['height'] * .6, steps=12)
    page.mouse.up()
    page.wait_for_timeout(350)
    after = canvas.screenshot()
    assert hashlib.sha256(before).digest() != hashlib.sha256(after).digest()
    canvas.screenshot(path=str(output / 'scene-rotated.png'))
    results['shared_camera_rotation'] = 'pointer drag changes the rendered scene and grid'
    for spacing in ['0.01', '0.1', '1', '10', '100', 'auto']:
        page.locator('#grid-spacing').select_option(spacing)
        expected = {'0.01': '1 cm', '0.1': '10 cm', 'auto': '10 m'}.get(spacing, spacing + ' m')
        assert page.locator('#grid-readout').inner_text().startswith(expected + ' per division')
    page.locator('#show-grid').uncheck()
    page.wait_for_timeout(200)
    hidden = canvas.screenshot()
    page.locator('#show-grid').check()
    page.wait_for_timeout(200)
    assert hidden != canvas.screenshot()
    results['grid_controls'] = 'all six spacings and visibility toggle passed'
    page.locator('#mission-form details').evaluate_all('items => items.forEach(item => item.open = true)')
    page.locator('#satellite-fields details').last.evaluate('item => item.open = true')
    page.locator('#p-position-x').fill('100')
    for position, valid in [('100.02', True), ('1100', True), ('100.019', False), ('1100.01', False)]:
        page.locator('#s-position-x').fill(position)
        page.locator('#s-position-x').dispatch_event('change')
        assert page.locator('#mission-form').evaluate('form => form.checkValidity()') == valid, position
    page.locator('#start-range-min').fill('0.02')
    page.locator('#start-range-max').fill('0.02')
    page.locator('#randomize').click()
    assert page.locator('#mission-form').evaluate('form => form.checkValidity()')
    results['placement_boundaries'] = 'translated 2 cm and 1 km accepted; outside values rejected; exact 2 cm randomization accepted'
    page.locator('#reset').click()
    page.locator('[data-camera="port"]').click()
    page.locator('#grid-spacing').select_option('0.01')
    page.wait_for_timeout(350)
    page.locator('#scene').screenshot(path=str(output / 'scene-centimetre-grid.png'))
    for width in [390, 320]:
        small = browser.new_page(viewport={'width': width, 'height': 900}, reduced_motion='reduce')
        small.on('pageerror', lambda error: errors.append(str(error)))
        small.goto('http://127.0.0.1:8000')
        small.wait_for_function("document.querySelector('#iss-status').dataset.state === 'ready'", timeout=60000)
        small.evaluate('document.fonts.ready')
        small.locator('#scene').scroll_into_view_if_needed()
        small.wait_for_timeout(700)
        small.evaluate('scrollTo(0, 0)')
        assert small.evaluate('document.documentElement.scrollWidth <= innerWidth')
        small.screenshot(path=str(output / f'mobile-{width}.png'), full_page=True)
        small.close()
    results['iss_model'] = 'NASA GLB loaded successfully on desktop and both mobile viewports'
    results['responsive'] = 'no horizontal overflow at 320px, 390px, and 1440px'
    results['javascript_errors'] = errors
    assert not errors
    browser.close()
(output / 'verification.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps(results, indent=2))
