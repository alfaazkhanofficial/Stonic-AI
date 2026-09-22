import { test, expect } from '@playwright/test';

test('dashboard, real service state, command palette, and MIC status', async ({page}) => {
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');
  await expect(page.getByText('LOCAL WORKSPACE',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'CONNECT AI',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'MIC',exact:true}).click();
  await expect(page.getByRole('button',{name:'MIC',exact:true})).not.toHaveAttribute('aria-pressed');
  await page.getByRole('button',{name:'Close panel'}).click();
  await page.keyboard.press('Control+k');
  await page.getByRole('textbox',{name:'Search commands'}).fill('diagnostic');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog')).toContainText('Workspace health: degraded');
  expect(errors).toEqual([]);
});

test('notes create, edit, reload, and delete through the backend', async ({page}) => {
  await page.goto('/');
  await page.getByRole('button',{name:'NOTES',exact:true}).click();
  await page.getByRole('button',{name:'Add note',exact:true}).click();
  const title=`Persistence ${Date.now()}`;
  await page.getByRole('textbox',{name:'note title'}).fill(title);
  await page.getByRole('textbox',{name:'note details'}).fill('This record should survive reloading.');
  await page.getByRole('button',{name:'Save note'}).click();
  await expect(page.getByRole('heading',{name:title})).toBeVisible();
  await page.reload();
  await page.getByRole('button',{name:'NOTES',exact:true}).click();
  await expect(page.getByRole('heading',{name:title})).toBeVisible();
  await page.getByRole('button',{name:`Edit ${title}`}).click();
  await page.getByRole('textbox',{name:'note details'}).fill('Updated text.');
  await page.getByRole('button',{name:'Save note'}).click();
  await expect(page.getByText('Updated text.',{exact:true})).toBeVisible();
  page.once('dialog',dialog=>dialog.accept());
  await page.getByRole('button',{name:`Delete ${title}`}).click();
  await expect(page.getByRole('heading',{name:title})).not.toBeVisible();
});

test('task completion and persistent configuration', async ({page}) => {
  await page.goto('/');
  await page.getByRole('button',{name:'TASKS',exact:true}).click();
  await page.getByRole('button',{name:'Add task',exact:true}).click();
  const title=`Task ${Date.now()}`;
  await page.getByRole('textbox',{name:'task title'}).fill(title);
  await page.getByRole('button',{name:'Save task'}).click();
  const task = page.locator('.record-card').filter({has:page.getByRole('heading',{name:title})});
  await task.getByRole('button',{name:'Complete task'}).click();
  await expect(task.getByRole('button',{name:'Reopen task'})).toBeVisible();
  await page.getByRole('button',{name:/Soul Your preferences/}).click();
  await page.getByLabel('Your name',{exact:true}).fill('Workspace Tester');
  await page.getByRole('button',{name:'Save changes'}).click();
  await expect(page.getByRole('status')).toContainText('Saved.');
  await page.reload();
  await page.getByRole('button',{name:/Soul Your preferences/}).click();
  await expect(page.getByLabel('Your name',{exact:true})).toHaveValue('Workspace Tester');
  await page.getByRole('button',{name:'Reset Your name',exact:true}).click();
  await page.getByRole('button',{name:'Save changes'}).click();
  await page.getByRole('button',{name:'Close panel'}).click();
  await page.getByRole('button',{name:'TASKS',exact:true}).click();
  page.once('dialog',dialog=>dialog.accept());
  await page.getByRole('button',{name:`Delete ${title}`}).click();
});

test('local status chat and visual flow are functional', async ({page}) => {
  await page.goto('/');
  await page.getByRole('textbox',{name:'Message STONIC'}).fill('/status');
  await page.getByRole('button',{name:'Send message'}).click();
  await expect(page.locator('.message-assistant').last()).toContainText('CPU:');
  await page.getByRole('button',{name:'Create a flow',exact:true}).click();
  await page.getByRole('textbox',{name:'Flow steps'}).fill('Plan\nBuild\nVerify');
  await page.getByRole('button',{name:'Create flow',exact:true}).click();
  await expect(page.locator('.flow-preview')).toContainText('Verify');
});

test('unsaved records are protected when changing tabs', async ({page}) => {
  await page.goto('/');
  await page.getByRole('button',{name:'NOTES',exact:true}).click();
  await page.getByRole('button',{name:'Add note',exact:true}).click();
  await page.getByRole('textbox',{name:'note title'}).fill('Unsaved draft');
  page.once('dialog',dialog=>dialog.dismiss());
  await page.getByRole('button',{name:'TASKS',exact:true}).click();
  await expect(page.getByRole('textbox',{name:'note title'})).toHaveValue('Unsaved draft');
  page.once('dialog',dialog=>dialog.accept());
  await page.getByRole('button',{name:'TASKS',exact:true}).click();
  await expect(page.getByRole('textbox',{name:'note title'})).not.toBeVisible();
});

for(const [width,height] of [[1920,1080],[1440,900],[1366,768],[1240,620],[1024,768],[768,1024],[390,844]]) {
  test(`layout stays within bounds at ${width}x${height}`, async ({page}) => {
    await page.setViewportSize({width,height});await page.goto('/');
    await expect(page.getByRole('button',{name:'CONNECT AI',exact:true})).toBeVisible();
    const overflow = await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+1);
    expect(overflow).toBe(false);
    if(width >= 1051) {
      const bottom = await page.locator('.composer-footnote').boundingBox();
      expect(bottom!.y + bottom!.height).toBeLessThanOrEqual(height);
      const capability = await page.getByRole('button',{name:'MIC',exact:true}).boundingBox();
      expect(capability!.y + capability!.height).toBeLessThanOrEqual(height);
    }
    await page.screenshot({path:`.runtime/screenshots/stonic-${width}.png`,fullPage:true});
  });
}
