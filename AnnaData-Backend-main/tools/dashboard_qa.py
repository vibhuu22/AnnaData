"""Read-only authenticated browser smoke check; credentials never logged."""
import asyncio, base64, json, os, subprocess, sys, tempfile, time
from pathlib import Path
import requests, websockets
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'AnnaData-Frontend-main/tools'))
from phone_shots import Tab, CHROME
async def main():
    output=Path(sys.argv[1]); output.mkdir(parents=True,exist_ok=True)
    profile=Path(tempfile.gettempdir())/'annadata-admin-v2-qa'
    proc=subprocess.Popen([CHROME,'--headless=new','--remote-debugging-port=9334',f'--user-data-dir={profile}','--no-first-run','--no-default-browser-check','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(30):
            try:
                requests.get('http://127.0.0.1:9334/json/version',timeout=1);break
            except requests.RequestException: await asyncio.sleep(.3)
        target=requests.put('http://127.0.0.1:9334/json/new?about:blank',timeout=5).json()
        async with websockets.connect(target['webSocketDebuggerUrl'],max_size=20_000_000) as ws:
            tab=Tab(ws)
            await tab.call('Page.enable')
            await tab.call('Emulation.setDeviceMetricsOverride',width=1440,height=1050,deviceScaleFactor=1,mobile=False)
            await tab.call('Page.navigate',url='http://127.0.0.1:8766/admin')
            await asyncio.sleep(1)
            token=dotenv_values(ROOT/'.env.admin').get('ADMIN_API_TOKEN') or dotenv_values(ROOT/'.env').get('ADMIN_API_TOKEN')
            if not token: raise RuntimeError('Admin credential not configured')
            await tab.js("document.querySelector('#admin-token').value="+json.dumps(token)+";document.querySelector('#login-form').requestSubmit()")
            for _ in range(60):
                if await tab.js("!document.querySelector('#workspace').hidden"): break
                await asyncio.sleep(.5)
            else: raise RuntimeError('Dashboard login did not complete')
            for section in ['overview','adoption','efficiency','diversity','feedback','health','reviews','guide','model_info']:
                await tab.js("document.querySelector('[data-view=\""+section+"\"]').click()")
                status=await tab.js("({title:document.querySelector('#page-title').textContent,content:document.querySelector('#content').innerText.length,overflow:document.documentElement.scrollWidth>innerWidth})")
                assert status['content']>100 and not status['overflow'], (section,status)
                print(section, status,flush=True)
                if section in ['overview','efficiency','diversity','feedback']:
                    shot=await tab.call('Page.captureScreenshot',format='png')
                    (output/(section+'.png')).write_bytes(base64.b64decode(shot['data']))
            await tab.js("document.querySelector('[data-view=overview]').click();document.querySelector('#audience').value='farmer';document.querySelector('#audience').dispatchEvent(new Event('change'))")
            for _ in range(100):
                if await tab.js("document.querySelector('#loading').hidden"): break
                await asyncio.sleep(.3)
            else: raise RuntimeError('Filter refresh did not finish')
            assert await tab.js("data.conversations.every(g=>g.audience==='farmer') && (data.metrics.participants>0 || document.querySelector('#content').innerText.includes('Not measured'))")
            print('Farmer filter and empty-state semantics: passed',flush=True)
            await tab.js("document.querySelector('#audience').value='all';document.querySelector('#audience').dispatchEvent(new Event('change'))")
            for _ in range(100):
                if await tab.js("document.querySelector('#loading').hidden"): break
                await asyncio.sleep(.3)
            else: raise RuntimeError('Filter refresh did not finish')
            await tab.call('Emulation.setDeviceMetricsOverride',width=390,height=844,deviceScaleFactor=1,mobile=True)
            for section in ['overview','adoption','efficiency','diversity','feedback','health','guide']:
                await tab.js("document.querySelector('[data-view=\""+section+"\"]').click()")
                assert not await tab.js('document.documentElement.scrollWidth>innerWidth'),section
            await tab.js("document.querySelector('[data-view=overview]').click()")
            shot=await tab.call('Page.captureScreenshot',format='png')
            (output/'phone.png').write_bytes(base64.b64decode(shot['data']))
            await tab.js("data.detailed.feedback.available=false;data.detailed.feedback.total=null;data.detailed.feedback.positive=null;data.detailed.feedback.coverage=null;view='feedback';render()")
            assert await tab.js("document.querySelector('#content').innerText.includes('Ratings are currently unavailable')")
            await tab.js("document.querySelector('#logout').click()")
            assert await tab.js("document.querySelector('#workspace').hidden && document.querySelector('#content').innerText==='' && token===''")
            print('Phone widths and logout: passed',flush=True)
    finally:
        proc.terminate()
        proc.wait(timeout=10)
if __name__=='__main__': asyncio.run(main())
