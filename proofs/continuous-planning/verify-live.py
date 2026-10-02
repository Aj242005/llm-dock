"""One real Vertex call; record live physics during its pending response."""
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

output = Path('.impeccable/review/continuous-planning')
output.mkdir(parents=True, exist_ok=True)
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(args=['--enable-webgl', '--use-gl=angle', '--use-angle=swiftshader'])
    page = browser.new_page(viewport={'width':1440, 'height':1000})
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto('http://127.0.0.1:8000')
    page.get_by_text('Backend connected', exact=True).wait_for()
    page.wait_for_function("document.querySelector('#iss-status').dataset.state === 'ready'", timeout=60000)
    page.locator('#mission-form details').evaluate_all('items => items.forEach(item => item.open = true)')
    page.locator('#s-velocity-x').fill('-0.05')
    page.locator('#p-velocity-x').fill('0.01')
    page.locator('#cadence').fill('500')
    page.locator('#rl-advisor').check()
    page.locator('#s-velocity-x').dispatch_event('change')
    invalid = page.locator('#mission-form').evaluate("form => [...form.querySelectorAll('input,select')].filter(e => !e.checkValidity()).map(e => ({id:e.id,value:e.value,error:e.validationMessage}))")
    assert not invalid, invalid
    if os.environ.get('DOCKING_VERIFY_RESUME_ID'):
        session_id = os.environ['DOCKING_VERIFY_RESUME_ID']
        prefix = '/api/v1/docking/sessions/' + session_id
        resumed = {'session_id':session_id,'summary_url':prefix,'stream_url':prefix+'/stream'}
        page.route('**/api/v1/docking/simulate',lambda route: route.fulfill(status=202,json=resumed))
    with page.expect_response('**/api/v1/docking/simulate') as created:
        page.locator('#start').click()
    assert created.value.status == 202, created.value.text()
    urls = created.value.json()
    page.wait_for_function("parseFloat(document.querySelector('#time').textContent) >= 2", timeout=15000)
    export_url = 'http://127.0.0.1:8000' + urls['summary_url'] + '/export'
    export = page.request.get(export_url).json()
    pending = [e for e in export['events'] if e['type']=='telemetry' and e.get('planning_pending')]
    assert len(pending) >= 2
    assert pending[-1]['sim_time_s'] > pending[0]['sim_time_s']
    assert pending[-1]['range_m'] != pending[0]['range_m']
    assert pending[-1]['primary']['position_m'] != pending[0]['primary']['position_m']
    page.screenshot(path=str(output/'desktop-live.png'),full_page=True)
    page.locator('#scene').screenshot(path=str(output/'scene-live.png'))
    page.wait_for_function("document.querySelectorAll('.decision').length > 0",timeout=150000)
    export = page.request.get(export_url).json()
    decision = next(e for e in export['events'] if e['type']=='llm_decision')
    assert decision['source']=='vertex',decision['source']
    assert decision['applied']
    assert decision['plan_age_s'] > 0
    assert decision['sim_time_s'] > decision['snapshot_sim_time_s']
    page.screenshot(path=str(output/'desktop-plan-applied.png'),full_page=True)
    page.locator('#cancel').click()
    page.wait_for_function("document.querySelector('#phase').textContent.startsWith('Stopped')",timeout=5000)
    export = page.request.get(export_url).json()
    (output/'vertex-session.json').write_text(json.dumps(export,indent=2),encoding='utf-8')
    for width in [390,320]:
        page.set_viewport_size({'width':width,'height':900})
        page.locator('#scene').scroll_into_view_if_needed()
        page.wait_for_timeout(600)
        page.evaluate('scrollTo(0,0)')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(output/f'mobile-{width}.png'),full_page=True)
    results = {
        'provider':'vertex', 'model':export['request']['config']['model'],
        'planning_motion':{'first_time_s':pending[0]['sim_time_s'],'last_time_s':pending[-1]['sim_time_s'],
        'first_range_m':pending[0]['range_m'],'last_range_m':pending[-1]['range_m'],
        'first_primary_position_m':pending[0]['primary']['position_m'],'last_primary_position_m':pending[-1]['primary']['position_m']},
        'plan_age_s':decision['plan_age_s'],'plan_applied':decision['applied'],
        'stop':export['summary']['failure_reason'],'javascript_errors':errors,
        'scope':'One real Vertex + PPO session at 1x with initial velocities; verifies continued physics, not docking success statistics.',
    }
    assert not errors
    (output/'verification.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(results,indent=2))
    browser.close()
