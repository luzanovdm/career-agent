import {chromium} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';
const backend=process.env.CAREER_BACKEND_ROOT,workspace='/tmp/career-story-makeup-owner-kit4';
const env={...process.env,CAREER_AGENT_DEVELOPMENT:'1',CAREER_AGENT_DEVELOPMENT_ASSETS:join(process.cwd(),'review-candidate-kit4'),PYTHONDONTWRITEBYTECODE:'1'};
const cli=(...args)=>JSON.parse(execFileSync('python3',[backend+'/scripts/career.py','--workspace',workspace,...args],{env,encoding:'utf8'}));
execFileSync('python3',['demo/seed_stories.py',backend,workspace,'makeup'],{env,encoding:'utf8'});
execFileSync('python3',[backend+'/scripts/career.py','--workspace',workspace,'command'],{env,encoding:'utf8',input:JSON.stringify({request_id:randomUUID(),expected_revision:cli('context').revision,intent:'preferences.set',input:{theme:'system',ui_locale:'ru'}})});
const launch=cli('ui','open','--no-browser');
const browser=await chromium.launch({headless:true,executablePath:process.env.CAREER_UI_CHROMIUM});
try {
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 await page.goto(launch.url);
 await page.locator('.stage-strip').waitFor();
 if(await page.locator('.stage-strip').getByRole('radio').count()!==6)throw new Error('Expected six stages.');
 await page.screenshot({path:'demo-screenshots/owner-kit4-confirmed.png',fullPage:true});
 await browser.close();
 // Obtain a separate one-use capability for the user's browser; never print it.
 const fresh=cli('ui','open','--no-browser');
 execFileSync('open',[fresh.url],{encoding:'utf8',stdio:'pipe'});
 const evidence={base_url:new URL(fresh.url).origin,build:fresh.release_id,ui_sha256:'f383bf5fcdda8ee6b73acc84f8e24a4c44868644a212d3f131e3dbae9cb75bae',workspace,fictional:true,headless_render_verified:true,os_browser_open_exit:0,interactive_browser_pixels_inspected:false,left_running:true,old_previews_untouched:[63442,50891],backend_acceptance:'Development preview; full1.0 backend acceptance remains pending.'};
 writeFileSync('evidence/owner-preview-kit4.json',JSON.stringify(evidence,null,2)+'\n');
 console.log(JSON.stringify(evidence));
} catch(error) {await browser.close();console.error(String(error.message).replace(/#launch=[^\s)]+/g,'#launch=[redacted]'));process.exitCode=1}
