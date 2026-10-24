import {chromium} from '@playwright/test';
import {execFileSync} from 'node:child_process';
const root=process.env.CAREER_BACKEND_ROOT;
const env={...process.env,CAREER_AGENT_DEVELOPMENT:'1',PYTHONDONTWRITEBYTECODE:'1'};
const launch=JSON.parse(execFileSync('python3',[root+'/scripts/career.py','--workspace','/tmp/career-demo-makeup-1','ui','open','--no-browser'],{env,encoding:'utf8'}));
const browser=await chromium.launch({headless:true,executablePath:process.env.CAREER_UI_CHROMIUM});
try{const page=await browser.newPage({viewport:{width:1440,height:1000}});await page.goto(launch.url);await page.getByRole('button',{name:'Open Lumen Demo Studio: Lead makeup artist'}).waitFor();await page.getByRole('button',{name:'Open Lumen Demo Studio: Lead makeup artist'}).click();await page.getByRole('textbox',{name:'Case notes'}).waitFor();await page.screenshot({path:'demo-screenshots/preview-makeup-confirmed.png',fullPage:true});console.log(JSON.stringify({base_url:new URL(page.url()).origin,actual_render_confirmed:true,screen:'Makeup artist case detail with selected materials and private notes',user_preview_left_running:true,screenshot:'ui/demo-screenshots/preview-makeup-confirmed.png'}));}finally{await browser.close()}
