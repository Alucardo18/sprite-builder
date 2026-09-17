import { chromium } from 'playwright';
import path from 'path';
import fs from 'fs';
import { execSync } from 'child_process';

const RAW_DIR = path.resolve('./hyperframes-showcase/assets/raw_recordings');
const CLIPS_DIR = path.resolve('./hyperframes-showcase/assets/video_clips');

if (!fs.existsSync(RAW_DIR)) fs.mkdirSync(RAW_DIR, { recursive: true });
if (!fs.existsSync(CLIPS_DIR)) fs.mkdirSync(CLIPS_DIR, { recursive: true });

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function smoothMoveTo(page, targetX, targetY, steps = 25) {
  await page.mouse.move(targetX, targetY, { steps });
}

async function smoothMoveToLocator(page, locator, steps = 25) {
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
        width: 26px;
        height: 26px;
        border: 2.5px solid #00f2fe;
        background: rgba(0, 242, 254, 0.25);
        border-radius: 50%;
        pointer-events: none;
        z-index: 999999;
        transform: translate(-50%, -50%);
        transition: transform 0.08s ease, background 0.15s, border-color 0.15s;
        box-shadow: 0 0 16px rgba(0, 242, 254, 0.8), 0 0 30px rgba(79, 172, 254, 0.4);
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
        cursor.style.background = 'rgba(255, 75, 145, 0.7)';
        cursor.style.borderColor = '#ff4b91';
        cursor.style.boxShadow = '0 0 24px rgba(255, 75, 145, 0.9)';
      });

      window.addEventListener('mouseup', () => {
        cursor.style.transform = 'translate(-50%, -50%) scale(1)';
        cursor.style.background = 'rgba(0, 242, 254, 0.25)';
        cursor.style.borderColor = '#00f2fe';
        cursor.style.boxShadow = '0 0 16px rgba(0, 242, 254, 0.8)';
      });
    });
  });
}

function convertWebmToMp4(webmPath, mp4Path, targetFps = 30) {
  console.log(`Converting ${path.basename(webmPath)} -> ${path.basename(mp4Path)}`);
  execSync(
    `ffmpeg -y -i "${webmPath}" -c:v libx264 -pix_fmt yuv420p -r ${targetFps} -preset medium -crf 18 "${mp4Path}"`,
    { stdio: 'inherit' }
  );
}

// ------------------------------------------------------------------------
// CLIP 1: Sprite Builder · Fondo y Poses del Zorro Místico (~20.5s)
// ------------------------------------------------------------------------
async function recordSpritePoses(browser) {
  console.log('\n--- Recording Clip 1: Sprite Builder Fondo y Poses ---');
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: { dir: RAW_DIR, size: { width: 1920, height: 1080 } },
  });
  const page = await context.newPage();
  await injectCursor(page);

  await page.goto('http://localhost:8501/?page=sprites', { waitUntil: 'networkidle' });
  await sleep(1500);

  // Mover cursor a la cabecera / badges de la sesión del zorro
  await smoothMoveTo(page, 400, 250, 30);
  await sleep(1000);

  // Tab 1. Fondo
  const tab1 = page.getByRole('tab', { name: /1\. Fondo/i });
  await smoothMoveToLocator(page, tab1, 20);
  await tab1.click();
  await sleep(800);

  // Mover cursor a los controles de tolerancia y limpieza
  await smoothMoveTo(page, 550, 520, 25);
  await sleep(1200);
  await smoothMoveTo(page, 650, 600, 20);
  await sleep(1000);

  // Tab 2. Preparar poses
  const tab2 = page.getByRole('tab', { name: /2\. Preparar poses/i });
  await smoothMoveToLocator(page, tab2, 25);
  await tab2.click();
  await sleep(1000);

  // Scroll suave al lienzo para enfocar las 12 poses del zorro místico
  await page.evaluate(async () => {
    const el = document.querySelector('section[data-testid="stMain"]') || document.querySelector('.main');
    if (!el) return;
    const start = el.scrollTop;
    const target = 520;
    const steps = 30;
    for (let i = 1; i <= steps; i++) {
      el.scrollTop = start + (target - start) * (i / steps);
      await new Promise(r => setTimeout(r, 20));
    }
  });
  await sleep(800);

  // Mover cursor a lo largo de las 12 poses de la cuadrícula
  await smoothMoveTo(page, 450, 550, 30);
  await sleep(1200);
  await smoothMoveTo(page, 800, 550, 35);
  await sleep(1200);
  await smoothMoveTo(page, 1150, 550, 35);
  await sleep(1200);

  // Fila inferior (perfil aullando)
  await smoothMoveTo(page, 1150, 750, 30);
  await sleep(1200);
  await smoothMoveTo(page, 600, 750, 35);
  await sleep(1500);

  // Clic en Guardar mapa provisional si está visible
  const saveBtn = page.locator('button').filter({ hasText: 'Guardar mapa provisional' });
  if (await saveBtn.isVisible()) {
    await smoothMoveToLocator(page, saveBtn, 25);
    await saveBtn.click();
    await sleep(2000);
  } else {
    await sleep(2000);
  }

  await context.close();
  const videoFile = await page.video().path();
  const targetMp4 = path.join(CLIPS_DIR, 'clip_sprites_poses.mp4');
  convertWebmToMp4(videoFile, targetMp4);
}

// ------------------------------------------------------------------------
// CLIP 2: Sprite Builder · Layer Studio, Animación GIF y Export (~22s)
// ------------------------------------------------------------------------
async function recordSpriteGif(browser) {
  console.log('\n--- Recording Clip 2: Sprite Builder GIF y Layer Studio ---');
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: { dir: RAW_DIR, size: { width: 1920, height: 1080 } },
  });
  const page = await context.newPage();
  await injectCursor(page);

  await page.goto('http://localhost:8501/?page=sprites', { waitUntil: 'networkidle' });
  await sleep(1500);

  // Tab 3. Alineación & anchors
  const tab3 = page.getByRole('tab', { name: /3\. Alineación/i });
  await smoothMoveToLocator(page, tab3, 25);
  await tab3.click();
  await sleep(1200);

  // Scroll suave al Estudio de capas
  await page.evaluate(async () => {
    const el = document.querySelector('section[data-testid="stMain"]') || document.querySelector('.main');
    if (!el) return;
    const start = el.scrollTop;
    const target = 480;
    const steps = 30;
    for (let i = 1; i <= steps; i++) {
      el.scrollTop = start + (target - start) * (i / steps);
      await new Promise(r => setTimeout(r, 20));
    }
  });
  await sleep(1000);

  // Mover cursor a las capas (Retoque, Fuente IA)
  await smoothMoveTo(page, 400, 520, 25);
  await sleep(1200);

  // Toggle Onion skin
  const onionToggle = page.locator('text=Onion skin');
  if (await onionToggle.isVisible()) {
    await smoothMoveToLocator(page, onionToggle, 25);
    await onionToggle.click();
    await sleep(1500);
  }

  // Mover cursor al control de FPS de reproducción
  await smoothMoveTo(page, 800, 500, 25);
  await sleep(1200);

  // Mover cursor a los botones de frames (Frame ->)
  const nextFrameBtn = page.locator('button').filter({ hasText: 'Frame →' });
  if (await nextFrameBtn.isVisible()) {
    for (let f = 0; f < 3; f++) {
      await smoothMoveToLocator(page, nextFrameBtn, 15);
      await nextFrameBtn.click();
      await sleep(700);
    }
  }
  await sleep(1000);

  // Tab 5. Export
  const tab5 = page.getByRole('tab', { name: /5\. Export/i });
  await smoothMoveToLocator(page, tab5, 25);
  await tab5.click();
  await sleep(1000);

  // Scroll suave a los controles de exportación GIF
  await page.evaluate(async () => {
    const el = document.querySelector('section[data-testid="stMain"]') || document.querySelector('.main');
    if (!el) return;
    const start = el.scrollTop;
    const target = 720;
    const steps = 30;
    for (let i = 1; i <= steps; i++) {
      el.scrollTop = start + (target - start) * (i / steps);
      await new Promise(r => setTimeout(r, 20));
    }
  });
  await sleep(1000);

  // Activar checkbox Exportar preview GIF
  const gifCheckbox = page.locator('text=Exportar preview GIF');
  if (await gifCheckbox.isVisible()) {
    await smoothMoveToLocator(page, gifCheckbox, 20);
    await gifCheckbox.click();
    await sleep(1500);
  }

  // Mover a la previsualización final con crosshairs
  await smoothMoveTo(page, 1200, 600, 25);
  await sleep(2500);

  await context.close();
  const videoFile = await page.video().path();
  const targetMp4 = path.join(CLIPS_DIR, 'clip_sprites_gif.mp4');
  convertWebmToMp4(videoFile, targetMp4);
}

// ------------------------------------------------------------------------
// CLIP 3: Tile Builder · Wheel Picker y Variante de Textura (~22s)
// ------------------------------------------------------------------------
async function recordTileWheel(browser) {
  console.log('\n--- Recording Clip 3: Tile Builder Wheel Picker y Textura ---');
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: { dir: RAW_DIR, size: { width: 1920, height: 1080 } },
  });
  const page = await context.newPage();
  await injectCursor(page);

  await page.goto('http://localhost:8501/?page=tilesets', { waitUntil: 'networkidle' });
  await sleep(1500);

  // Mover cursor al botón superior / título de Tileset Builder
  await smoothMoveTo(page, 300, 100, 25);
  await sleep(1000);

  // Mover al Asistente: ✨ Generar desde Cero (Procedural)
  const procTab = page.locator('text=Generar desde Cero');
  if (await procTab.isVisible()) {
    await smoothMoveToLocator(page, procTab, 20);
    await sleep(800);
  }

  // Interacción con el Wheel Picker de Color Base (Relleno)
  const primaryColorPicker = page.locator('div[data-testid="stColorPicker"]').first();
  if (await primaryColorPicker.isVisible()) {
    await smoothMoveToLocator(page, primaryColorPicker, 25);
    await primaryColorPicker.click();
    await sleep(1500);
    // Presionar escape para cerrar el popover de la rueda de color
    await page.keyboard.press('Escape');
    await sleep(600);
  }

  // Interacción con el Wheel Picker de Color Secundario
  const secondaryColorPicker = page.locator('div[data-testid="stColorPicker"]').nth(1);
  if (await secondaryColorPicker.isVisible()) {
    await smoothMoveToLocator(page, secondaryColorPicker, 25);
    await secondaryColorPicker.click();
    await sleep(1500);
    await page.keyboard.press('Escape');
    await sleep(600);
  }

  // Desplegar y mostrar Variante de Textura (Receta Visual)
  const recipeSelect = page.locator('div[data-testid="stSelectbox"]').filter({ hasText: /Zelda|Receta|Estilo/i }).or(page.locator('div[data-testid="stSelectbox"]').nth(1));
  if (await recipeSelect.isVisible()) {
    await smoothMoveToLocator(page, recipeSelect, 25);
    await recipeSelect.click();
    await sleep(1200);
    // Mostrar opciones y seleccionar Zelda Top-Down
    const zeldaOpt = page.locator('li[role="option"]').filter({ hasText: /Zelda/i });
    if (await zeldaOpt.isVisible()) {
      await smoothMoveToLocator(page, zeldaOpt, 15);
      await zeldaOpt.click();
    } else {
      await page.keyboard.press('Escape');
    }
    await sleep(1000);
  }

  // Botón Crear y Activar Terreno Procedural
  const createBtn = page.locator('button').filter({ hasText: 'Crear y Activar Terreno Procedural' });
  if (await createBtn.isVisible()) {
    await smoothMoveToLocator(page, createBtn, 25);
    await createBtn.click();
    await sleep(2500);
  }

  // Mover a Set Activo y status
  await smoothMoveTo(page, 320, 150, 25);
  await sleep(2000);

  await context.close();
  const videoFile = await page.video().path();
  const targetMp4 = path.join(CLIPS_DIR, 'clip_tiles_wheel.mp4');
  convertWebmToMp4(videoFile, targetMp4);
}

// ------------------------------------------------------------------------
// CLIP 4: Tile Builder · Pattern Studio y Map Tester (~19s)
// ------------------------------------------------------------------------
async function recordTileMap(browser) {
  console.log('\n--- Recording Clip 4: Pattern Studio y Map Tester ---');
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: { dir: RAW_DIR, size: { width: 1920, height: 1080 } },
  });
  const page = await context.newPage();
  await injectCursor(page);

  await page.goto('http://localhost:8501/?page=tilesets', { waitUntil: 'networkidle' });
  await sleep(1500);

  // Tab Pattern Studio
  const tabPattern = page.getByRole('tab', { name: /Pattern Studio/i });
  if (await tabPattern.isVisible()) {
    await smoothMoveToLocator(page, tabPattern, 25);
    await tabPattern.click();
    await sleep(1000);
  }

  // Scroll suave al atlas de 47 losas y sus variantes
  await page.evaluate(async () => {
    const el = document.querySelector('section[data-testid="stMain"]') || document.querySelector('.main');
    if (!el) return;
    const start = el.scrollTop;
    const target = 500;
    const steps = 30;
    for (let i = 1; i <= steps; i++) {
      el.scrollTop = start + (target - start) * (i / steps);
      await new Promise(r => setTimeout(r, 20));
    }
  });
  await sleep(800);

  // Mover cursor a través de las opciones de transición (Pasto sobre tierra, etc.)
  await smoothMoveTo(page, 450, 600, 30);
  await sleep(1200);
  await smoothMoveTo(page, 850, 600, 30);
  await sleep(1200);

  // Tab Map Tester
  const tabMap = page.getByRole('tab', { name: /Map Tester/i });
  if (await tabMap.isVisible()) {
    await smoothMoveToLocator(page, tabMap, 25);
    await tabMap.click();
    await sleep(1200);
  }

  // Scroll suave al lienzo de juego / mapa autotileado
  await page.evaluate(async () => {
    const el = document.querySelector('section[data-testid="stMain"]') || document.querySelector('.main');
    if (!el) return;
    const start = el.scrollTop;
    const target = 400;
    const steps = 30;
    for (let i = 1; i <= steps; i++) {
      el.scrollTop = start + (target - start) * (i / steps);
      await new Promise(r => setTimeout(r, 20));
    }
  });
  await sleep(1000);

  // Clic en el botón de generar mapa procedural o pintar en el lienzo
  const genMapBtn = page.locator('button').filter({ hasText: /Generar|Random|Procedural|Mapa/i }).first();
  if (await genMapBtn.isVisible()) {
    await smoothMoveToLocator(page, genMapBtn, 25);
    await genMapBtn.click();
    await sleep(1500);
  }

  // Mover cursor sobre el mapa autotileado mostrando las costas y bordes
  await smoothMoveTo(page, 700, 550, 30);
  await sleep(1000);
  await smoothMoveTo(page, 1100, 550, 35);
  await sleep(1500);

  await context.close();
  const videoFile = await page.video().path();
  const targetMp4 = path.join(CLIPS_DIR, 'clip_tiles_map.mp4');
  convertWebmToMp4(videoFile, targetMp4);
}

// ------------------------------------------------------------------------
// RUN ALL RECORDINGS
// ------------------------------------------------------------------------
async function run() {
  console.log('Launching Chromium for Real Flow Showcase Recording...');
  const browser = await chromium.launch({ headless: true });

  try {
    await recordSpritePoses(browser);
    await recordSpriteGif(browser);
    await recordTileWheel(browser);
    await recordTileMap(browser);
    console.log('\n✅ All real flow clips recorded and converted successfully!');
  } catch (err) {
    console.error('Error during recording:', err);
  } finally {
    await browser.close();
  }
}

run();
