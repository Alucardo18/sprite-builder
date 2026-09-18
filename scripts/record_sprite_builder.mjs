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
// SCENE 2: Remoción de Fondo y Limpieza de Píxeles (25.5s)
// ----------------------------------------------------
async function recordScene2(browser) {
  console.log('\n--- Recording Scene 2: Remoción de fondo ---');
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    recordVideo: { dir: RECORDINGS_DIR, size: { width: 1920, height: 1080 } }
  });
  const page = await context.newPage();
  await injectCursor(page);

  await page.goto('http://localhost:8501/?page=sprites', { waitUntil: 'networkidle' });
  await sleep(2500);

  // Focus on Tab 1. Fondo
  const tab1 = page.locator('[role="tab"]:has-text("1. Fondo")').first();
  if (await tab1.count() > 0) {
    await smoothMoveToLocator(page, tab1, 25);
    await sleep(600);
    await tab1.click();
    await sleep(1500);
  }

  // Move cursor to sidebar: "Remoción de fondo" controls
  const tolSlider = page.locator('div[data-testid="stSlider"]:has-text("Tolerancia RGB"), div[data-testid="stSlider"]').first();
  if (await tolSlider.count() > 0) {
    await smoothMoveToLocator(page, tolSlider, 30);
    await sleep(2000);
  }

  const fringeToggle = page.locator('label:has-text("Cleanup de fringe")').first();
  if (await fringeToggle.count() > 0) {
    await smoothMoveToLocator(page, fringeToggle, 25);
    await sleep(1500);
  }

  const outlineToggle = page.locator('label:has-text("Preservar outline")').first();
  if (await outlineToggle.count() > 0) {
    await smoothMoveToLocator(page, outlineToggle, 25);
    await sleep(1500);
  }

  // Move smoothly to main canvas showing the sprite sheet with transparent background
  await page.mouse.wheel(0, 300);
  await sleep(1000);

  await smoothMoveTo(page, 960, 560, 35);
  await sleep(2500);
  await smoothMoveTo(page, 1100, 620, 30);
  await sleep(2500);
  await smoothMoveTo(page, 850, 520, 30);
  await sleep(4000);

  const video = page.video();
  await page.close();
  await context.close();
  const videoPath = await video.path();
  convertWebmToMp4(videoPath, path.join(CLIPS_DIR, 'clip_sprite2_background.mp4'));
}

// ----------------------------------------------------
// SCENE 3: Preparar Poses y Asignación de Frames (23.0s)
// ----------------------------------------------------
async function recordScene3(browser) {
  console.log('\n--- Recording Scene 3: Preparar poses ---');
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    recordVideo: { dir: RECORDINGS_DIR, size: { width: 1920, height: 1080 } }
  });
  const page = await context.newPage();
  await injectCursor(page);

  await page.goto('http://localhost:8501/?page=sprites', { waitUntil: 'networkidle' });
  await sleep(2500);

  // Click Tab 2. Preparar & Alinear
  const tab2 = page.locator('[role="tab"]:has-text("2. Preparar")').first();
  if (await tab2.count() > 0) {
    await tab2.click();
    await page.waitForTimeout(1000);
    console.log('Switched to Tab 2. Preparar & Alinear');
    await sleep(2000);
  }

  // Scroll down slightly to canvas
  await page.mouse.wheel(0, 260);
  await sleep(1500);

  // Move cursor around the 4 poses on top row
  await smoothMoveTo(page, 520, 680, 30);
  await sleep(2000);
  await smoothMoveTo(page, 660, 680, 25);
  await sleep(1500);
  await smoothMoveTo(page, 820, 680, 25);
  await sleep(1500);
  await smoothMoveTo(page, 980, 680, 25);
  await sleep(2000);

  // Move to the frame boundary handle
  await smoothMoveTo(page, 450, 620, 25);
  await sleep(1000);
  await page.mouse.down();
  await sleep(200);
  await page.mouse.up();
  await sleep(4000);

  const video = page.video();
  await page.close();
  await context.close();
  const videoPath = await video.path();
  convertWebmToMp4(videoPath, path.join(CLIPS_DIR, 'clip_sprite3_prepare.mp4'));
}

// ----------------------------------------------------
// SCENE 4: Alineación Multi-Anchor (27.0s)
// ----------------------------------------------------
async function recordScene4(browser) {
  console.log('\n--- Recording Scene 4: Alineación & anchors ---');
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    recordVideo: { dir: RECORDINGS_DIR, size: { width: 1920, height: 1080 } }
  });
  const page = await context.newPage();
  await injectCursor(page);

  await page.goto('http://localhost:8501/?page=sprites', { waitUntil: 'networkidle' });
  await sleep(2500);

  // Click Tab 3. Alineación & anchors
  const tab3 = page.locator('[role="tab"]:has-text("3. Alineación & anchors")').first();
  if (await tab3.count() > 0) {
    await smoothMoveToLocator(page, tab3, 30);
    await sleep(800);
    await tab3.click();
    console.log('Switched to Tab 3. Alineación & anchors');
    await sleep(2000);
  }

  // Sidebar: animation profile controls (Idle / Walk / Attack)
  const profileControl = page.locator('div[data-testid="stSegmentedControl"], button:has-text("Walk"), button:has-text("Idle")').first();
  if (await profileControl.count() > 0) {
    await smoothMoveToLocator(page, profileControl, 30);
    await sleep(2000);
  }

  // Scroll to alignment canvas controls
  await page.mouse.wheel(0, 320);
  await sleep(1200);

  // Point to button "Autoalinear todo"
  const autoBtn = page.locator('button:has-text("Autoalinear todo")').first();
  if (await autoBtn.count() > 0) {
    await smoothMoveToLocator(page, autoBtn, 30);
    await sleep(1000);
    await autoBtn.click();
    console.log('Clicked Autoalinear todo');
    await sleep(2500);
  }

  // Inspect the multi-anchor crosshairs on the character body
  await smoothMoveTo(page, 720, 680, 30);
  await sleep(2500);
  await smoothMoveTo(page, 950, 680, 30);
  await sleep(2500);
  await smoothMoveTo(page, 1180, 680, 30);
  await sleep(4000);

  const video = page.video();
  await page.close();
  await context.close();
  const videoPath = await video.path();
  convertWebmToMp4(videoPath, path.join(CLIPS_DIR, 'clip_sprite4_align.mp4'));
}

// ----------------------------------------------------
// SCENE 5: Cortes Finales y Export (26.0s)
// ----------------------------------------------------
async function recordScene5(browser) {
  console.log('\n--- Recording Scene 5: Cortes finales y Export ---');
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    recordVideo: { dir: RECORDINGS_DIR, size: { width: 1920, height: 1080 } }
  });
  const page = await context.newPage();
  await injectCursor(page);

  await page.goto('http://localhost:8501/?page=sprites', { waitUntil: 'networkidle' });
  await sleep(2500);

  // Click Tab 4. Cortes finales
  const tab4 = page.locator('[role="tab"]:has-text("4. Cortes finales")').first();
  if (await tab4.count() > 0) {
    await smoothMoveToLocator(page, tab4, 25);
    await sleep(800);
    await tab4.click();
    console.log('Switched to Tab 4. Cortes finales');
    await sleep(2500);
  }

  // Inspect uniform layout controls
  await page.mouse.wheel(0, 180);
  await sleep(1500);

  // Click Tab 5. Export
  const tab5 = page.locator('[role="tab"]:has-text("5. Export")').first();
  if (await tab5.count() > 0) {
    await smoothMoveToLocator(page, tab5, 25);
    await sleep(800);
    await tab5.click();
    console.log('Switched to Tab 5. Export');
    await sleep(2500);
  }

  // Inspect "Hoja nativa completa" export button
  const exportBtn = page.locator('button:has-text("Exportar hoja nativa completa")').first();
  if (await exportBtn.count() > 0) {
    await smoothMoveToLocator(page, exportBtn, 30);
    await sleep(2000);
  }

  // Scroll down to individual frames and AtlasTexture
  await page.mouse.wheel(0, 320);
  await sleep(1500);

  const individualToggle = page.locator('label:has-text("Exportar frames individuales")').first();
  if (await individualToggle.count() > 0) {
    await smoothMoveToLocator(page, individualToggle, 25);
    await sleep(2000);
  }

  await smoothMoveTo(page, 960, 700, 30);
  await sleep(3500);

  const video = page.video();
  await page.close();
  await context.close();
  const videoPath = await video.path();
  convertWebmToMp4(videoPath, path.join(CLIPS_DIR, 'clip_sprite5_export.mp4'));
}

async function main() {
  console.log('Launching browser for Sprite Builder tutorial recording...');
  const browser = await chromium.launch({
    headless: true,
    args: ['--enable-webgl', '--use-gl=angle']
  });

  try {
    await recordScene2(browser);
    await recordScene3(browser);
    await recordScene4(browser);
    await recordScene5(browser);
    console.log('\nAll Sprite Builder scene recordings completed successfully!');
  } finally {
    await browser.close();
  }
}

main().catch(err => {
  console.error('Fatal recording error:', err);
  process.exit(1);
});
