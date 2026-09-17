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

// -------------------------------------------------------------
// ESCENA 2: Sprite Builder Workflow (Fondo, Alineación, Cortes) ~ 25s
// -------------------------------------------------------------
async function recordSpriteWorkflow(browser) {
  console.log('\n--- Recording Clip: Sprite Builder Workflow (~25s) ---');
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    recordVideo: {
      dir: RECORDINGS_DIR,
      size: { width: 1920, height: 1080 },
    },
  });

  const page = await context.newPage();
  await injectCursor(page);

  await page.goto('http://localhost:8501/?page=sprites', { waitUntil: 'networkidle' });
  await sleep(1500);

  // Seleccionar la sesión de jaguar guerrero azteca
  const selectbox = page.locator('div[data-testid="stSelectbox"]').first();
  if (await selectbox.isVisible()) {
    await smoothMoveToLocator(page, selectbox, 25);
    await selectbox.click();
    await sleep(600);
    const option = page.locator('li[role="option"]').filter({ hasText: 'sheet-20260913T034239' });
    if (await option.isVisible()) {
      await smoothMoveToLocator(page, option, 20);
      await option.click();
      await sleep(1500);
    } else {
      await page.keyboard.press('Escape');
    }
  }

  // Pestaña 1. Fondo
  const tabFondo = page.getByRole('tab', { name: /1\. Fondo/i });
  if (await tabFondo.isVisible()) {
    await smoothMoveToLocator(page, tabFondo, 25);
    await tabFondo.click();
    await sleep(1200);
  }

  // Mover cursor por controles de fondo (color picker, tolerancia, fringe)
  await smoothMoveTo(page, 520, 480, 25);
  await sleep(1500);
  await smoothMoveTo(page, 650, 560, 20);
  await sleep(1800);
  await smoothMoveTo(page, 1100, 520, 25);
  await sleep(1500);

  // Pestaña 3. Alineación & anchors
  const tabAlign = page.getByRole('tab', { name: /3\. Alineación/i });
  if (await tabAlign.isVisible()) {
    await smoothMoveToLocator(page, tabAlign, 30);
    await tabAlign.click();
    await sleep(1500);
  }

  // Scroll a la zona de anclaje y autoalinear
  await page.evaluate(() => window.scrollBy({ top: 400, behavior: 'smooth' }));
  await sleep(1200);

  const autoCenterBtn = page.getByRole('button', { name: /Autoalinear/i }).first();
  if (await autoCenterBtn.isVisible()) {
    await smoothMoveToLocator(page, autoCenterBtn, 25);
    await autoCenterBtn.click();
    await sleep(3000);
  }

  // Pestaña 4. Cortes finales
  const tabCuts = page.getByRole('tab', { name: /4\. Cortes/i });
  if (await tabCuts.isVisible()) {
    await smoothMoveToLocator(page, tabCuts, 25);
    await tabCuts.click();
    await sleep(1500);
  }

  await smoothMoveTo(page, 960, 600, 25);
  await sleep(3500);

  await context.close();
  const videoFile = await page.video().path();
  const targetMp4 = path.join(CLIPS_DIR, 'clip_showcase_sprites.mp4');
  convertWebmToMp4(videoFile, targetMp4);
}

// -------------------------------------------------------------
// ESCENA 4: Tileset Builder · Blob 47 Orgánico (~22s)
// -------------------------------------------------------------
async function recordBlob47(browser) {
  console.log('\n--- Recording Clip: Tileset Builder Blob 47 (~22s) ---');
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    recordVideo: {
      dir: RECORDINGS_DIR,
      size: { width: 1920, height: 1080 },
    },
  });

  const page = await context.newPage();
  await injectCursor(page);

  await page.goto('http://localhost:8501/?page=tilesets', { waitUntil: 'networkidle' });
  await sleep(1500);

  // Ir a Pattern Studio
  const tabPattern = page.getByRole('tab', { name: /Pattern Studio/i });
  if (await tabPattern.isVisible()) {
    await smoothMoveToLocator(page, tabPattern, 20);
    await tabPattern.click();
    await sleep(1500);
  }

  // Clic en preset "Pasto sobre tierra"
  const presetGrassDirt = page.getByRole('button', { name: /Pasto sobre tierra/i }).first();
  if (await presetGrassDirt.isVisible()) {
    await smoothMoveToLocator(page, presetGrassDirt, 25);
    await presetGrassDirt.click();
    await sleep(2500);
  }

  // Mover cursor sobre el componente interactivo (grilla de 47 tiles)
  await smoothMoveTo(page, 550, 480, 25);
  await sleep(1500);
  await smoothMoveTo(page, 850, 480, 25);
  await sleep(1500);

  // Dibujar en el canvas sandbox si está disponible
  const frame = page.frameLocator('iframe').first();
  const canvas = frame.locator('canvas').first();
  if (await canvas.isVisible()) {
    const box = await canvas.boundingBox();
    if (box) {
      const cx = box.x + box.width * 0.4;
      const cy = box.y + box.height * 0.4;
      await smoothMoveTo(page, cx, cy, 20);
      await page.mouse.down();
      await smoothMoveTo(page, cx + 180, cy, 25);
      await smoothMoveTo(page, cx + 180, cy + 140, 25);
      await smoothMoveTo(page, cx, cy + 140, 25);
      await smoothMoveTo(page, cx, cy, 25);
      await page.mouse.up();
      await sleep(2000);

      // Segunda pasada para añadir una bahía o sendero
      await smoothMoveTo(page, cx + 90, cy + 70, 20);
      await page.mouse.down();
      await smoothMoveTo(page, cx + 240, cy + 70, 25);
      await page.mouse.up();
      await sleep(3500);
    }
  } else {
    await smoothMoveTo(page, 960, 600, 30);
    await sleep(6000);
  }

  await context.close();
  const videoFile = await page.video().path();
  const targetMp4 = path.join(CLIPS_DIR, 'clip_showcase_blob47.mp4');
  convertWebmToMp4(videoFile, targetMp4);
}

// -------------------------------------------------------------
// ESCENA 5: Tileset Builder · Dual Grid 15 (~21s)
// -------------------------------------------------------------
async function recordDualGrid(browser) {
  console.log('\n--- Recording Clip: Tileset Builder Dual Grid 15 (~21s) ---');
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    recordVideo: {
      dir: RECORDINGS_DIR,
      size: { width: 1920, height: 1080 },
    },
  });

  const page = await context.newPage();
  await injectCursor(page);

  await page.goto('http://localhost:8501/?page=tilesets', { waitUntil: 'networkidle' });
  await sleep(1500);

  // Ir a Pattern Studio
  const tabPattern = page.getByRole('tab', { name: /Pattern Studio/i });
  if (await tabPattern.isVisible()) {
    await smoothMoveToLocator(page, tabPattern, 20);
    await tabPattern.click();
    await sleep(1500);
  }

  // Dentro del iframe de Pattern Studio, hacer clic en "Build Dual Grid · 15"
  const frame = page.frameLocator('iframe').first();
  const buildDualBtn = frame.locator('#buildDual, #buildDualInspector, #contextDual, button:has-text("Dual Grid · 15"), button:has-text("Dual Grid 15")').first();

  if (await buildDualBtn.isVisible()) {
    console.log('Found Dual Grid 15 button in iframe!');
    await smoothMoveToLocator(page, buildDualBtn, 25);
    await buildDualBtn.click();
    await sleep(2500);
  } else {
    const dualRadio = frame.locator('input[value="dual_grid_15"]').first();
    if (await dualRadio.isVisible()) {
      await smoothMoveToLocator(page, dualRadio, 20);
      await dualRadio.click();
      await sleep(2500);
    }
  }

  // Mover cursor sobre las 15 variaciones
  await smoothMoveTo(page, 600, 500, 25);
  await sleep(1500);
  await smoothMoveTo(page, 850, 500, 25);
  await sleep(1500);

  // Dibujar en el canvas sandbox para ver la grilla dual resolviendo esquinas
  const canvas = frame.locator('canvas').first();
  if (await canvas.isVisible()) {
    const box = await canvas.boundingBox();
    if (box) {
      const cx = box.x + box.width * 0.35;
      const cy = box.y + box.height * 0.35;
      await smoothMoveTo(page, cx, cy, 20);
      await page.mouse.down();
      await smoothMoveTo(page, cx + 220, cy, 25);
      await smoothMoveTo(page, cx + 220, cy + 120, 25);
      await smoothMoveTo(page, cx, cy + 120, 25);
      await smoothMoveTo(page, cx, cy, 25);
      await page.mouse.up();
      await sleep(2500);

      // Trazo adicional en esquina
      await smoothMoveTo(page, cx + 110, cy + 60, 20);
      await page.mouse.down();
      await smoothMoveTo(page, cx + 180, cy + 60, 20);
      await page.mouse.up();
      await sleep(4000);
    }
  } else {
    await smoothMoveTo(page, 960, 600, 30);
    await sleep(6500);
  }

  await context.close();
  const videoFile = await page.video().path();
  const targetMp4 = path.join(CLIPS_DIR, 'clip_showcase_dualgrid.mp4');
  convertWebmToMp4(videoFile, targetMp4);
}

// -------------------------------------------------------------
// ESCENA 6: Map Tester y Exportación (~20s)
// -------------------------------------------------------------
async function recordMapTesterAndExport(browser) {
  console.log('\n--- Recording Clip: Map Tester and Export (~20s) ---');
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    recordVideo: {
      dir: RECORDINGS_DIR,
      size: { width: 1920, height: 1080 },
    },
  });

  const page = await context.newPage();
  await injectCursor(page);

  await page.goto('http://localhost:8501/?page=tilesets', { waitUntil: 'networkidle' });
  await sleep(1500);

  // Clic en pestaña Map Tester
  const tabMap = page.getByRole('tab', { name: /Map Tester/i });
  if (await tabMap.isVisible()) {
    await smoothMoveToLocator(page, tabMap, 20);
    await tabMap.click();
    await sleep(1500);
  }

  // Clic en Generar Mapa Procedural
  const btnGenMap = page.getByRole('button', { name: /Generar Mapa Procedural/i }).first();
  if (await btnGenMap.isVisible()) {
    await smoothMoveToLocator(page, btnGenMap, 25);
    await btnGenMap.click();
    await sleep(3000);
  }

  // Mover cursor por el mapa generado
  await smoothMoveTo(page, 800, 450, 25);
  await sleep(1500);
  await smoothMoveTo(page, 1100, 480, 25);
  await sleep(1500);

  // Scroll abajo para mostrar los paquetes de exportación
  await page.evaluate(() => window.scrollBy({ top: 550, behavior: 'smooth' }));
  await sleep(1500);

  // Mover cursor sobre opciones de exportación (Godot, Unity, Tiled)
  const godotBtn = page.getByRole('button', { name: /Godot/i }).first();
  if (await godotBtn.isVisible()) {
    await smoothMoveToLocator(page, godotBtn, 25);
    await sleep(1500);
  } else {
    await smoothMoveTo(page, 800, 720, 20);
    await sleep(1500);
  }

  await smoothMoveTo(page, 1050, 720, 20);
  await sleep(3500);

  await context.close();
  const videoFile = await page.video().path();
  const targetMp4 = path.join(CLIPS_DIR, 'clip_showcase_maptester.mp4');
  convertWebmToMp4(videoFile, targetMp4);
}

// -------------------------------------------------------------
// MAIN RUNNER
// -------------------------------------------------------------
async function main() {
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });

  try {
    await recordSpriteWorkflow(browser);
    await recordBlob47(browser);
    await recordDualGrid(browser);
    await recordMapTesterAndExport(browser);
    console.log('\n Updated showcase clips recorded and converted successfully!');
  } finally {
    await browser.close();
  }
}

main().catch(err => {
  console.error('Recording error:', err);
  process.exit(1);
});
