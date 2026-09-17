import { chromium } from 'playwright';
import path from 'path';
import fs from 'fs';
import { execSync } from 'child_process';

const RECORDINGS_DIR = path.resolve('./tutorial-video/public/recordings');
const CLIPS_DIR = path.resolve('./tutorial-video/public/clips');

if (!fs.existsSync(RECORDINGS_DIR)) fs.mkdirSync(RECORDINGS_DIR, { recursive: true });
if (!fs.existsSync(CLIPS_DIR)) fs.mkdirSync(CLIPS_DIR, { recursive: true });

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function smoothMoveTo(page, targetX, targetY, steps = 30) {
  await page.mouse.move(targetX, targetY, { steps });
}

async function smoothMoveToLocator(page, locator, steps = 30) {
  const box = await locator.boundingBox();
  if (box) {
    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    await page.mouse.move(x, y, { steps });
    return { x, y };
  }
  return null;
}

function injectCursor(page) {
  return page.addInitScript(() => {
    window.addEventListener('DOMContentLoaded', () => {
      const cursor = document.createElement('div');
      cursor.id = 'demo-cursor';
      cursor.style.cssText = `
        position: fixed;
        width: 24px;
        height: 24px;
        border: 2px solid #57dfbc;
        background: rgba(87, 223, 188, 0.25);
        border-radius: 50%;
        pointer-events: none;
        z-index: 999999;
        transform: translate(-50%, -50%);
        transition: transform 0.08s ease, width 0.15s, height 0.15s, background 0.15s;
        box-shadow: 0 0 14px rgba(87, 223, 188, 0.7);
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
        cursor.style.background = 'rgba(255, 104, 152, 0.7)';
        cursor.style.borderColor = '#ff6898';
        cursor.style.boxShadow = '0 0 22px rgba(255, 104, 152, 0.9)';
      });

      window.addEventListener('mouseup', () => {
        cursor.style.transform = 'translate(-50%, -50%) scale(1)';
        cursor.style.background = 'rgba(87, 223, 188, 0.25)';
        cursor.style.borderColor = '#57dfbc';
        cursor.style.boxShadow = '0 0 14px rgba(87, 223, 188, 0.7)';
      });
    });
  });
}

function convertWebmToMp4(webmPath, mp4Path, targetFps = 60) {
  console.log(`Converting ${path.basename(webmPath)} -> ${path.basename(mp4Path)}`);
  execSync(
    `ffmpeg -y -i "${webmPath}" -c:v libx264 -pix_fmt yuv420p -r ${targetFps} -preset medium -crf 18 "${mp4Path}"`,
    { stdio: 'inherit' }
  );
}

// ----------------------------------------------------
// SCENE 2: Patrón 1 · Pasto sobre Tierra (25.5s)
// ----------------------------------------------------
async function recordScene2(browser) {
  console.log('\n--- Recording Scene 2: Pasto sobre Tierra ---');
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    recordVideo: { dir: RECORDINGS_DIR, size: { width: 1920, height: 1080 } }
  });
  const page = await context.newPage();
  await injectCursor(page);

  await page.goto('http://localhost:8501/?page=tilesets', { waitUntil: 'networkidle' });
  await sleep(2000);

  // Switch to Pattern Studio
  const studioTab = page.locator('[role="tab"]:has-text("Pattern Studio")').first();
  if (await studioTab.count() > 0) {
    await studioTab.click();
    await sleep(2000);
  }

  // Scroll down to Pattern Studio workspace
  await page.mouse.wheel(0, 420);
  await sleep(2000);

  const studioFrameEl = await page.waitForSelector('iframe[src*="terrain_pattern_studio"]', { timeout: 10000 });
  const studioFrame = await studioFrameEl.contentFrame();

  // Move smoothly to #blobGrassDirt button and click
  const btnGrassDirt = studioFrame.locator('#blobGrassDirt');
  await smoothMoveToLocator(page, btnGrassDirt, 35);
  await sleep(1000);
  await btnGrassDirt.click();
  console.log('Clicked #blobGrassDirt');
  await sleep(3000);

  // Inspect 47 generated autotiles
  const canvasEl = studioFrame.locator('#setCanvas');
  const cBox = await canvasEl.boundingBox();
  if (cBox) {
    await smoothMoveTo(page, cBox.x + cBox.width * 0.25, cBox.y + cBox.height * 0.3, 30);
    await sleep(2000);
    await smoothMoveTo(page, cBox.x + cBox.width * 0.65, cBox.y + cBox.height * 0.4, 30);
    await sleep(2500);
  }

  // Move to sandbox canvas and paint organic grass patches
  const sandboxEl = studioFrame.locator('#sandboxCanvas');
  const sBox = await sandboxEl.boundingBox();
  if (sBox) {
    // Draw patch 1
    await smoothMoveTo(page, sBox.x + sBox.width * 0.45, sBox.y + sBox.height * 0.45, 25);
    await sleep(500);
    await page.mouse.down();
    await sleep(250);
    await page.mouse.up();
    await sleep(1200);

    // Draw patch 2
    await smoothMoveTo(page, sBox.x + sBox.width * 0.55, sBox.y + sBox.height * 0.5, 25);
    await sleep(500);
    await page.mouse.down();
    await sleep(250);
    await page.mouse.up();
    await sleep(1500);

    // Hover around the seamless grass connection
    await smoothMoveTo(page, sBox.x + sBox.width * 0.5, sBox.y + sBox.height * 0.35, 30);
    await sleep(3500);
  }

  const video = page.video();
  await page.close();
  await context.close();
  const videoPath = await video.path();
  convertWebmToMp4(videoPath, path.join(CLIPS_DIR, 'clip2_grass_dirt.mp4'));
}

// ----------------------------------------------------
// SCENE 3: Patrón 2 · Tierra sobre Agua (23.5s)
// ----------------------------------------------------
async function recordScene3(browser) {
  console.log('\n--- Recording Scene 3: Tierra sobre Agua ---');
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    recordVideo: { dir: RECORDINGS_DIR, size: { width: 1920, height: 1080 } }
  });
  const page = await context.newPage();
  await injectCursor(page);

  await page.goto('http://localhost:8501/?page=tilesets', { waitUntil: 'networkidle' });
  await sleep(2000);

  const studioTab = page.locator('[role="tab"]:has-text("Pattern Studio")').first();
  if (await studioTab.count() > 0) {
    await studioTab.click();
    await sleep(2000);
  }

  await page.mouse.wheel(0, 420);
  await sleep(2000);

  const studioFrameEl = await page.waitForSelector('iframe[src*="terrain_pattern_studio"]', { timeout: 10000 });
  const studioFrame = await studioFrameEl.contentFrame();

  // Click #blobDirtWater button
  const btnDirtWater = studioFrame.locator('#blobDirtWater');
  await smoothMoveToLocator(page, btnDirtWater, 35);
  await sleep(1000);
  await btnDirtWater.click();
  console.log('Clicked #blobDirtWater');
  await sleep(3000);

  // Inspect dirt shoreline tiles with shadow depth
  const canvasEl = studioFrame.locator('#setCanvas');
  const cBox = await canvasEl.boundingBox();
  if (cBox) {
    await smoothMoveTo(page, cBox.x + cBox.width * 0.3, cBox.y + cBox.height * 0.7, 30);
    await sleep(2000);
    await smoothMoveTo(page, cBox.x + cBox.width * 0.7, cBox.y + cBox.height * 0.7, 30);
    await sleep(2000);
  }

  // Paint in sandbox: dirt island emerging from water
  const sandboxEl = studioFrame.locator('#sandboxCanvas');
  const sBox = await sandboxEl.boundingBox();
  if (sBox) {
    await smoothMoveTo(page, sBox.x + sBox.width * 0.5, sBox.y + sBox.height * 0.42, 25);
    await sleep(500);
    await page.mouse.down();
    await sleep(250);
    await page.mouse.up();
    await sleep(1200);

    await smoothMoveTo(page, sBox.x + sBox.width * 0.5, sBox.y + sBox.height * 0.58, 25);
    await sleep(500);
    await page.mouse.down();
    await sleep(250);
    await page.mouse.up();
    await sleep(1500);

    // Hover on coastal shadow transition
    await smoothMoveTo(page, sBox.x + sBox.width * 0.62, sBox.y + sBox.height * 0.5, 30);
    await sleep(3000);
  }

  const video = page.video();
  await page.close();
  await context.close();
  const videoPath = await video.path();
  convertWebmToMp4(videoPath, path.join(CLIPS_DIR, 'clip3_dirt_water.mp4'));
}

// ----------------------------------------------------
// SCENE 4: Patrón 3 · Pasto sobre Agua (22.0s)
// ----------------------------------------------------
async function recordScene4(browser) {
  console.log('\n--- Recording Scene 4: Pasto sobre Agua ---');
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    recordVideo: { dir: RECORDINGS_DIR, size: { width: 1920, height: 1080 } }
  });
  const page = await context.newPage();
  await injectCursor(page);

  await page.goto('http://localhost:8501/?page=tilesets', { waitUntil: 'networkidle' });
  await sleep(2000);

  const studioTab = page.locator('[role="tab"]:has-text("Pattern Studio")').first();
  if (await studioTab.count() > 0) {
    await studioTab.click();
    await sleep(2000);
  }

  await page.mouse.wheel(0, 420);
  await sleep(2000);

  const studioFrameEl = await page.waitForSelector('iframe[src*="terrain_pattern_studio"]', { timeout: 10000 });
  const studioFrame = await studioFrameEl.contentFrame();

  // Click #blobGrassWater button
  const btnGrassWater = studioFrame.locator('#blobGrassWater');
  await smoothMoveToLocator(page, btnGrassWater, 35);
  await sleep(1000);
  await btnGrassWater.click();
  console.log('Clicked #blobGrassWater');
  await sleep(3000);

  // Inspect cliff tiles
  const canvasEl = studioFrame.locator('#setCanvas');
  const cBox = await canvasEl.boundingBox();
  if (cBox) {
    await smoothMoveTo(page, cBox.x + cBox.width * 0.35, cBox.y + cBox.height * 0.7, 30);
    await sleep(2000);
  }

  // Paint in sandbox: floating green plateau
  const sandboxEl = studioFrame.locator('#sandboxCanvas');
  const sBox = await sandboxEl.boundingBox();
  if (sBox) {
    await smoothMoveTo(page, sBox.x + sBox.width * 0.42, sBox.y + sBox.height * 0.45, 25);
    await sleep(500);
    await page.mouse.down();
    await sleep(250);
    await page.mouse.up();
    await sleep(1200);

    await smoothMoveTo(page, sBox.x + sBox.width * 0.58, sBox.y + sBox.height * 0.55, 25);
    await sleep(500);
    await page.mouse.down();
    await sleep(250);
    await page.mouse.up();
    await sleep(1500);

    // Hover on steep cliff corners
    await smoothMoveTo(page, sBox.x + sBox.width * 0.5, sBox.y + sBox.height * 0.4, 30);
    await sleep(3000);
  }

  const video = page.video();
  await page.close();
  await context.close();
  const videoPath = await video.path();
  convertWebmToMp4(videoPath, path.join(CLIPS_DIR, 'clip4_grass_water.mp4'));
}

// ----------------------------------------------------
// SCENE 5: Map Tester & Exportación (25.5s)
// ----------------------------------------------------
async function recordScene5(browser) {
  console.log('\n--- Recording Scene 5: Map Tester & Exportación ---');
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    recordVideo: { dir: RECORDINGS_DIR, size: { width: 1920, height: 1080 } }
  });
  const page = await context.newPage();
  await injectCursor(page);

  await page.goto('http://localhost:8501/?page=tilesets', { waitUntil: 'networkidle' });
  await sleep(2000);

  // Click "Crear y Activar Terreno Procedural" to generate and populate the full complete tileset
  const btnCreateProcedural = page.locator('button:has-text("Crear y Activar Terreno Procedural")').first();
  if (await btnCreateProcedural.count() > 0) {
    await smoothMoveToLocator(page, btnCreateProcedural, 25);
    await sleep(500);
    await btnCreateProcedural.click();
    console.log('Clicked "Crear y Activar Terreno Procedural"');
    await sleep(2500);
  }

  // Click Map Tester tab
  const mapTab = page.locator('[role="tab"]:has-text("Map Tester")').first();
  if (await mapTab.count() > 0) {
    await smoothMoveToLocator(page, mapTab, 25);
    await sleep(600);
    await mapTab.click();
    console.log('Switched to Map Tester tab');
    await sleep(2500);
  }

  // Scroll to map preview
  await page.mouse.wheel(0, 320);
  await sleep(1500);

  // Click "Regenerar preset"
  const regenBtn = page.locator('button:has-text("Regenerar preset")').first();
  if (await regenBtn.count() > 0) {
    await smoothMoveToLocator(page, regenBtn, 25);
    await sleep(600);
    await regenBtn.click();
    console.log('Clicked Regenerar preset');
    await sleep(2500);
  }

  // Click "Aplicar en (X, Y)" to edit real-time
  const applyBtn = page.locator('button:has-text("Aplicar en (X, Y)")').first();
  if (await applyBtn.count() > 0) {
    await smoothMoveToLocator(page, applyBtn, 25);
    await sleep(600);
    await applyBtn.click();
    console.log('Clicked Aplicar en (X, Y)');
    await sleep(2000);
  }

  // Scroll down to Export section in Pattern Studio
  await page.mouse.wheel(0, -600);
  await sleep(800);

  const studioTab = page.locator('[role="tab"]:has-text("Pattern Studio")').first();
  if (await studioTab.count() > 0) {
    await smoothMoveToLocator(page, studioTab, 25);
    await studioTab.click();
    await sleep(1500);
  }

  await page.mouse.wheel(0, 1250);
  await sleep(1500);

  // Hover over Godot 4, Unity, Tiled export buttons
  const godotBtn = page.locator('button:has-text("Bundle Godot 4"), a:has-text("Bundle Godot 4")').first();
  if (await godotBtn.count() > 0) {
    await smoothMoveToLocator(page, godotBtn, 30);
    await sleep(1800);
  }

  const unityBtn = page.locator('button:has-text("Unity RuleTile"), a:has-text("Unity RuleTile")').first();
  if (await unityBtn.count() > 0) {
    await smoothMoveToLocator(page, unityBtn, 30);
    await sleep(1800);
  }

  const tiledBtn = page.locator('button:has-text("Tiled Map"), a:has-text("Tiled Map")').first();
  if (await tiledBtn.count() > 0) {
    await smoothMoveToLocator(page, tiledBtn, 30);
    await sleep(2500);
  }

  const video = page.video();
  await page.close();
  await context.close();
  const videoPath = await video.path();
  convertWebmToMp4(videoPath, path.join(CLIPS_DIR, 'clip5_map_export.mp4'));
}

async function main() {
  console.log('Launching browser for scene 5 recording...');
  const browser = await chromium.launch({
    headless: true,
    args: ['--enable-webgl', '--use-gl=angle']
  });

  try {
    await recordScene5(browser);
    console.log('\nScene 5 recording completed successfully!');
  } finally {
    await browser.close();
  }
}

main().catch(err => {
  console.error('Fatal recording error:', err);
  process.exit(1);
});
