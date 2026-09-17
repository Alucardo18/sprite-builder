import { chromium } from 'playwright';
import path from 'path';
import fs from 'fs';

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function smoothMoveTo(page, locator, steps = 25) {
  const box = await locator.boundingBox();
  if (box) {
    const targetX = box.x + box.width / 2;
    const targetY = box.y + box.height / 2;
    await page.mouse.move(targetX, targetY, { steps });
    return { x: targetX, y: targetY };
  }
  return null;
}

async function record() {
  const recordingDir = path.resolve('./tutorial-video/public/recordings');
  if (!fs.existsSync(recordingDir)) {
    fs.mkdirSync(recordingDir, { recursive: true });
  }

  console.log('Launching browser for 1080p recording...');
  const browser = await chromium.launch({
    headless: true,
    args: ['--enable-webgl', '--use-gl=angle']
  });

  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    recordVideo: {
      dir: recordingDir,
      size: { width: 1920, height: 1080 }
    }
  });

  const page = await context.newPage();

  // Inject visual cursor ring
  await page.addInitScript(() => {
    window.addEventListener('DOMContentLoaded', () => {
      const cursor = document.createElement('div');
      cursor.id = 'demo-cursor';
      cursor.style.cssText = `
        position: fixed;
        width: 22px;
        height: 22px;
        border: 2px solid #57dfbc;
        background: rgba(87, 223, 188, 0.25);
        border-radius: 50%;
        pointer-events: none;
        z-index: 999999;
        transform: translate(-50%, -50%);
        transition: transform 0.08s ease, width 0.15s, height 0.15s, background 0.15s;
        box-shadow: 0 0 12px rgba(87, 223, 188, 0.6);
        display: none;
      `;
      document.body.appendChild(cursor);

      window.addEventListener('mousemove', e => {
        cursor.style.display = 'block';
        cursor.style.left = e.clientX + 'px';
        cursor.style.top = e.clientY + 'px';
      });

      window.addEventListener('mousedown', () => {
        cursor.style.transform = 'translate(-50%, -50%) scale(0.75)';
        cursor.style.background = 'rgba(255, 104, 152, 0.6)';
        cursor.style.borderColor = '#ff6898';
        cursor.style.boxShadow = '0 0 20px rgba(255, 104, 152, 0.8)';
      });

      window.addEventListener('mouseup', () => {
        cursor.style.transform = 'translate(-50%, -50%) scale(1)';
        cursor.style.background = 'rgba(87, 223, 188, 0.25)';
        cursor.style.borderColor = '#57dfbc';
        cursor.style.boxShadow = '0 0 12px rgba(87, 223, 188, 0.6)';
      });
    });
  });

  console.log('=== ESCENA 1: Navegación e Introducción al Ecosistema (0s - 25s) ===');
  await page.goto('http://localhost:8501', { waitUntil: 'networkidle' });
  await sleep(4000);

  const tilesetLink = page.locator('a[data-page="tilesets"], a:has-text("Tileset Builder")').first();
  if (await tilesetLink.count() > 0) {
    await smoothMoveTo(page, tilesetLink, 40);
    await sleep(1000);
    await tilesetLink.click();
    console.log('Clicked Tileset Builder nav');
    await sleep(4000);
  } else {
    await page.goto('http://localhost:8501/?page=tilesets', { waitUntil: 'networkidle' });
    await sleep(4000);
  }

  // Switch to Pattern Studio
  const studioTab = page.locator('[role="tab"]:has-text("Pattern Studio")').first();
  if (await studioTab.count() > 0) {
    await smoothMoveTo(page, studioTab, 30);
    await sleep(800);
    await studioTab.click();
    console.log('Switched to Pattern Studio tab');
    await sleep(4000);
  }

  // Scroll down to Pattern Studio workspace
  await page.mouse.wheel(0, 420);
  await sleep(2500);

  const studioFrameElement = await page.waitForSelector('iframe[src*="terrain_pattern_studio"]', { timeout: 10000 }).catch(() => null);
  let studioFrame = null;
  if (studioFrameElement) {
    studioFrame = await studioFrameElement.contentFrame();
  }

  console.log('=== ESCENA 2: Patrón 1 · Pasto sobre Tierra (25s - 50s) ===');
  if (studioFrame) {
    const btnGrassDirt = studioFrame.locator('#blobGrassDirt');
    if (await btnGrassDirt.count() > 0) {
      await smoothMoveTo(page, btnGrassDirt, 35);
      await sleep(1500);
      await btnGrassDirt.click();
      console.log('Clicked "Pasto sobre tierra"');
      await sleep(3500);
    }

    // Inspect the 47 autotiles on setCanvas
    const canvasEl = studioFrame.locator('#setCanvas');
    if (await canvasEl.count() > 0) {
      await smoothMoveTo(page, canvasEl, 40);
      await sleep(3000);
    }

    // Paint in sandbox: natural patch of grass over dirt
    const sandboxEl = studioFrame.locator('#sandboxCanvas');
    if (await sandboxEl.count() > 0) {
      const sBox = await sandboxEl.boundingBox();
      if (sBox) {
        // Draw grass patch
        await page.mouse.move(sBox.x + sBox.width * 0.45, sBox.y + sBox.height * 0.45, { steps: 25 });
        await sleep(500);
        await page.mouse.down();
        await sleep(200);
        await page.mouse.up();
        await sleep(1000);

        await page.mouse.move(sBox.x + sBox.width * 0.55, sBox.y + sBox.height * 0.5, { steps: 20 });
        await sleep(400);
        await page.mouse.down();
        await sleep(200);
        await page.mouse.up();
        await sleep(2500);
      }
    }
  }

  console.log('=== ESCENA 3: Patrón 2 · Tierra sobre Agua (50s - 74s) ===');
  if (studioFrame) {
    const btnDirtWater = studioFrame.locator('#blobDirtWater');
    if (await btnDirtWater.count() > 0) {
      await smoothMoveTo(page, btnDirtWater, 35);
      await sleep(1500);
      await btnDirtWater.click();
      console.log('Clicked "Tierra sobre agua"');
      await sleep(3500);
    }

    // Inspect the coast/dirt tiles on setCanvas
    const canvasEl = studioFrame.locator('#setCanvas');
    if (await canvasEl.count() > 0) {
      await smoothMoveTo(page, canvasEl, 35);
      await sleep(3000);
    }

    // Paint an island in sandbox
    const sandboxEl = studioFrame.locator('#sandboxCanvas');
    if (await sandboxEl.count() > 0) {
      const sBox = await sandboxEl.boundingBox();
      if (sBox) {
        await page.mouse.move(sBox.x + sBox.width * 0.5, sBox.y + sBox.height * 0.4, { steps: 25 });
        await sleep(500);
        await page.mouse.down();
        await sleep(200);
        await page.mouse.up();
        await sleep(1000);

        await page.mouse.move(sBox.x + sBox.width * 0.5, sBox.y + sBox.height * 0.6, { steps: 20 });
        await sleep(400);
        await page.mouse.down();
        await sleep(200);
        await page.mouse.up();
        await sleep(2500);
      }
    }
  }

  console.log('=== ESCENA 4: Patrón 3 · Pasto sobre Agua (74s - 96s) ===');
  if (studioFrame) {
    const btnGrassWater = studioFrame.locator('#blobGrassWater');
    if (await btnGrassWater.count() > 0) {
      await smoothMoveTo(page, btnGrassWater, 35);
      await sleep(1500);
      await btnGrassWater.click();
      console.log('Clicked "Pasto sobre agua"');
      await sleep(3500);
    }

    // Inspect cliff tiles on setCanvas
    const canvasEl = studioFrame.locator('#setCanvas');
    if (await canvasEl.count() > 0) {
      await smoothMoveTo(page, canvasEl, 35);
      await sleep(3000);
    }

    // Draw cliff / floating green island in sandbox
    const sandboxEl = studioFrame.locator('#sandboxCanvas');
    if (await sandboxEl.count() > 0) {
      const sBox = await sandboxEl.boundingBox();
      if (sBox) {
        await page.mouse.move(sBox.x + sBox.width * 0.4, sBox.y + sBox.height * 0.45, { steps: 25 });
        await sleep(500);
        await page.mouse.down();
        await sleep(200);
        await page.mouse.up();
        await sleep(1000);

        await page.mouse.move(sBox.x + sBox.width * 0.6, sBox.y + sBox.height * 0.55, { steps: 20 });
        await sleep(400);
        await page.mouse.down();
        await sleep(200);
        await page.mouse.up();
        await sleep(2500);
      }
    }
  }

  console.log('=== ESCENA 5: Map Tester & Exportación (96s - 121s) ===');
  await page.mouse.wheel(0, -600);
  await sleep(1000);

  const mapTab = page.locator('[role="tab"]:has-text("Map Tester")').first();
  if (await mapTab.count() > 0) {
    await smoothMoveTo(page, mapTab, 30);
    await sleep(800);
    await mapTab.click();
    console.log('Switched to Map Tester');
    await sleep(3500);
  }

  await page.mouse.wheel(0, 320);
  await sleep(2000);

  const regenBtn = page.locator('button:has-text("Regenerar preset")').first();
  if (await regenBtn.count() > 0) {
    await smoothMoveTo(page, regenBtn, 30);
    await sleep(800);
    await regenBtn.click();
    console.log('Regenerated preset map');
    await sleep(3500);
  }

  const applyBtn = page.locator('button:has-text("Aplicar en (X, Y)")').first();
  if (await applyBtn.count() > 0) {
    await smoothMoveTo(page, applyBtn, 30);
    await sleep(800);
    await applyBtn.click();
    console.log('Applied brush stroke');
    await sleep(3000);
  }

  // Back to Pattern Studio for export options
  await page.mouse.wheel(0, -700);
  await sleep(1000);
  if (await studioTab.count() > 0) {
    await smoothMoveTo(page, studioTab, 25);
    await studioTab.click();
    await sleep(2500);
  }

  await page.mouse.wheel(0, 1150);
  await sleep(2000);

  const godotBtn = page.locator('button:has-text("Bundle Godot 4"), a:has-text("Bundle Godot 4")').first();
  if (await godotBtn.count() > 0) {
    await smoothMoveTo(page, godotBtn, 30);
    await sleep(1500);
  }

  const unityBtn = page.locator('button:has-text("Unity RuleTile"), a:has-text("Unity RuleTile")').first();
  if (await unityBtn.count() > 0) {
    await smoothMoveTo(page, unityBtn, 30);
    await sleep(1500);
  }

  const tiledBtn = page.locator('button:has-text("Tiled Map"), a:has-text("Tiled Map")').first();
  if (await tiledBtn.count() > 0) {
    await smoothMoveTo(page, tiledBtn, 30);
    await sleep(1500);
  }

  await sleep(4000);

  console.log('Closing browser context to finalize video save...');
  await page.close();
  await context.close();
  await browser.close();
  console.log('Recording completed successfully!');
}

record().catch(err => {
  console.error('Recording failed:', err);
  process.exit(1);
});
