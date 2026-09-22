import { test, expect } from '@playwright/test';

test('quick access CONFIG and system monitor use real panels',async({page})=>{
  await page.goto('/');await page.keyboard.press('Control+k');
  const grid=page.getByRole('navigation',{name:'Quick access'});
  await grid.getByRole('button',{name:'CONFIG',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'Configuration'})).toBeVisible();
  await page.getByRole('button',{name:'Close panel'}).click();
  await page.keyboard.press('Control+k');await grid.getByRole('button',{name:'SYSTEM',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'System monitor'})).toContainText('logical processors');
  await expect(page.getByRole('img',{name:'CPU usage sampled every two seconds'})).toBeVisible();
});

test('unsaved preference survives a declined panel switch',async({page})=>{
  await page.goto('/');await page.getByRole('button',{name:/Soul Your preferences/}).click();
  await page.getByLabel('Preference',{exact:true}).fill('Unsaved preference fixture');
  page.once('dialog',dialog=>dialog.dismiss());await page.keyboard.press('Control+k');
  await expect(page.getByLabel('Preference',{exact:true})).toHaveValue('Unsaved preference fixture');
  page.once('dialog',dialog=>dialog.accept());await page.keyboard.press('Control+k');
  await expect(page.getByRole('dialog',{name:'Command center'})).toBeVisible();
});

test('briefing reads actual reminders and exports a calendar',async({page,request})=>{
  const title=`Calendar fixture ${Date.now()}`;
  const created=await (await request.post('/api/schedules',{data:{title,due_at:new Date(Date.now()+3600000).toISOString()}})).json();
  try{
    await page.goto('/');await page.keyboard.press('Control+k');await page.getByRole('navigation',{name:'Quick access'}).getByRole('button',{name:'EVENTS',exact:true}).click();
    await expect(page.locator('.briefing')).toContainText(title);
    const mark=page.getByRole('button',{name:'Mark briefing reviewed',exact:true});
    if(await mark.count())await mark.click();
    await expect(page.getByRole('button',{name:'Briefing reviewed',exact:true})).toBeVisible();
    const download=page.waitForEvent('download');
    await page.getByRole('button',{name:'Export reminders to calendar'}).click();
    expect((await download).suggestedFilename()).toBe('stonic-reminders.ics');
    const calendar=await (await request.get('/api/productivity/calendar')).text();
    expect(calendar).toContain(`SUMMARY:${title}`);expect(calendar).toContain('BEGIN:VCALENDAR');
  }finally{await request.post(`/api/schedules/${created.data.id}/cancel`);}
});

test('pinned panels coexist, move with keyboard, restore and stay on screen', async ({page})=>{
  await page.goto('/');
  await page.getByRole('button',{name:/Memory \d+ saved memories/}).click();
  const memory=page.getByRole('dialog',{name:'Memory',exact:true});
  await memory.getByRole('button',{name:'Pin panel',exact:true}).click();
  await expect(memory).toHaveAttribute('aria-modal','false');
  const before=await memory.boundingBox();
  await memory.getByLabel('Move Memory panel with Alt and arrow keys').focus();
  await page.keyboard.press('Alt+ArrowRight');
  const after=await memory.boundingBox();
  expect(after!.x).toBeGreaterThan(before!.x);
  await page.keyboard.press('Control+,');
  await expect(memory).toBeVisible();
  await expect(page.getByRole('dialog',{name:'Configuration'})).toBeVisible();
  await page.getByRole('dialog',{name:'Configuration'}).getByRole('button',{name:'Close panel'}).click();
  await memory.getByRole('button',{name:'Minimize panel'}).click();
  await expect(memory.getByRole('button',{name:'Restore panel'})).toBeVisible();
  await memory.getByRole('button',{name:'Restore panel'}).click();
  await page.reload();
  await expect(memory).toBeVisible();
  await page.setViewportSize({width:768,height:600});
  const restored=await memory.boundingBox();
  expect(restored!.x).toBeGreaterThanOrEqual(0);
  expect(restored!.x+restored!.width).toBeLessThanOrEqual(768);
  await memory.getByRole('button',{name:'Close panel'}).click();
});

test('approved preference editor persists and forgets a correction',async({page})=>{
  await page.goto('/');
  await page.getByRole('button',{name:/Soul Your preferences/}).click();
  const preference=`Test preference ${Date.now()}`;
  await page.getByLabel('Preference',{exact:true}).fill(preference);
  await page.getByRole('button',{name:'Approve and save'}).click();
  await expect(page.locator('.job-card').filter({hasText:preference})).toBeVisible();
  await page.reload();
  await page.getByRole('button',{name:/Soul Your preferences/}).click();
  const card=page.locator('.job-card').filter({hasText:preference});
  await expect(card).toBeVisible();
  page.once('dialog',d=>d.accept());
  await card.getByRole('button',{name:'Forget',exact:true}).click();
  await expect(card).not.toBeVisible();
});

test('approval UI displays bound inputs and denial executes no action',async({page,request})=>{
  const response=await request.post('/api/computer/action',{data:{tool:'computer.window',arguments:{hwnd:1,expected_pid:1,expected_title:'Acceptance fixture only',action:'close'}}});
  expect(response.ok()).toBeTruthy();
  const job=await response.json();
  expect(job.status).toBe('waiting_approval');
  await page.goto('/');
  await page.getByRole('button',{name:'Expand task activity'}).click();
  const dialog=page.getByRole('dialog',{name:'Task activity',exact:true});
  const card=dialog.locator('.job-card').filter({hasText:'Acceptance fixture only'});
  await expect(card).toContainText('expected_pid');
  await card.getByRole('button',{name:'Deny',exact:true}).click();
  await expect(dialog.locator('.job-card').filter({hasText:job.goal}).first()).toContainText('cancelled');
  const jobs=await (await request.get('/api/jobs')).json();
  const denied=jobs.find((j:{id:string})=>j.id===job.id);
  expect(denied.steps[0].attempts).toBe(0);
});

test('memory categories persist independently of search',async({page})=>{
  await page.goto('/');await page.getByRole('button',{name:/Memory \d+ saved memories/}).click();
  await page.getByRole('button',{name:'Add memory',exact:true}).click();
  const title=`Environment test ${Date.now()}`;
  await page.getByLabel('memory title').fill(title);
  await page.getByLabel('Memory type',{exact:true}).selectOption('environment');
  await page.getByRole('button',{name:'Save memory'}).click();
  await page.getByLabel('Memory type',{exact:true}).selectOption('user');
  await expect(page.getByRole('heading',{name:title})).not.toBeVisible();
  await page.getByLabel('Memory type',{exact:true}).selectOption('environment');
  await expect(page.getByRole('heading',{name:title})).toBeVisible();
  page.once('dialog',d=>d.accept());
  await page.getByRole('button',{name:`Delete ${title}`}).click();
});
