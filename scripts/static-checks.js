const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(process.env.BAMBIKU_STATIC_ROOT || path.resolve(__dirname, '..'));
const failures = [];

function fail(message) {
  failures.push(message);
}

function walk(dir, predicate, results = []) {
  if (!fs.existsSync(dir)) return results;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (
      entry.name === 'node_modules' ||
      entry.name === '.git' ||
      entry.name === '.venv' ||
      entry.name === '.codex-logs' ||
      entry.name === 'dist' ||
      entry.name === '__pycache__'
    ) {
      continue;
    }
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(fullPath, predicate, results);
    } else if (!predicate || predicate(fullPath)) {
      results.push(fullPath);
    }
  }
  return results;
}

function rel(filePath) {
  return path.relative(root, filePath).replace(/\\/g, '/');
}

function read(filePath) {
  return fs.readFileSync(filePath, 'utf8').replace(/^\uFEFF/, '');
}

function checkJson() {
  for (const filePath of walk(path.join(root, 'data'), file => file.endsWith('.json'))) {
    try {
      JSON.parse(read(filePath));
    } catch (err) {
      fail(`${rel(filePath)}: invalid JSON (${err.message})`);
    }
  }
}

function checkI18nCoverage() {
  const i18nPath = path.join(root, 'data', 'i18n.json');
  if (!fs.existsSync(i18nPath)) {
    fail('data/i18n.json: translation catalog is missing');
    return;
  }

  let catalog;
  try {
    catalog = JSON.parse(read(i18nPath));
  } catch (err) {
    return;
  }

  const languages = ['ru', 'en'];
  for (const language of languages) {
    if (!catalog[language] || typeof catalog[language] !== 'object') {
      fail(`data/i18n.json: ${language} catalog is missing`);
    }
  }
  if (languages.some(language => !catalog[language])) return;

  const constantsPath = path.join(root, 'js', 'core', 'constants.js');
  const context = { window: {} };
  try {
    vm.runInNewContext(read(constantsPath), context, { filename: constantsPath });
  } catch (err) {
    fail(`js/core/constants.js: cannot inspect fallback translations (${err.message})`);
  }
  const fallback = context.window.Bambiku?.constants?.fallbackI18n || {};

  const allKeys = new Set([...Object.keys(catalog.ru), ...Object.keys(catalog.en)]);
  for (const key of allKeys) {
    for (const language of languages) {
      if (!Object.prototype.hasOwnProperty.call(catalog[language], key)) {
        fail(`data/i18n.json: ${language}.${key} is missing`);
      }
    }
  }

  const usedKeys = new Set();
  // BuKaMiKu is a separate application with its own translation catalog.
  // Keep the Bambiku catalog check scoped to the central frontend.
  const sourceFiles = [
    path.join(root, 'index.html'),
    ...walk(path.join(root, 'pages'), file => /\.(?:html|js)$/.test(file)),
    ...walk(path.join(root, 'js'), file => /\.(?:html|js)$/.test(file)),
  ].filter(file => fs.existsSync(file));
  const htmlKeyPattern = /data-i18n(?:-html|-ph)?\s*=\s*["']([A-Za-z0-9_.:-]+)["']/g;
  const jsKeyPattern = /\b(?:ui\.)?t\(\s*["']([A-Za-z0-9_.:-]+)["']\s*[,)]/g;
  for (const filePath of sourceFiles) {
    const source = read(filePath);
    for (const match of source.matchAll(htmlKeyPattern)) usedKeys.add(match[1]);
    for (const match of source.matchAll(jsKeyPattern)) usedKeys.add(match[1]);
  }
  for (const key of usedKeys) {
    for (const language of languages) {
      const inCatalog = Object.prototype.hasOwnProperty.call(catalog[language], key);
      const inFallback = Object.prototype.hasOwnProperty.call(fallback[language] || {}, key);
      if (!inCatalog && !inFallback) {
        fail(`i18n: ${language}.${key} is used by the frontend but not translated`);
      }
    }
  }

  const dynamicFamilies = [
    ['hero_kawaui_state_', 18],
    ['hero_kawaui_log_', 18],
    ['hero_entity_condition_', 23],
    ['hero_condition_log_', 23],
    ['hero_protocol_state_', 18],
    ['hero_protocol_log_', 18],
  ];
  for (const [prefix, count] of dynamicFamilies) {
    for (let index = 1; index <= count; index += 1) {
      const key = `${prefix}${index}`;
      for (const language of languages) {
        if (!String(catalog[language][key] || '').trim()) {
          fail(`data/i18n.json: ${language}.${key} is required by a dynamic translation family`);
        }
      }
    }
  }

  const forbiddenRuleTerms = [
    /\bback-?end\b/i,
    /\bfront-?end\b/i,
    /\bserver[- ]side\b/i,
    /\bapi\b/i,
    /\u0441\u0435\u0440\u0432\u0435\u0440/i,
  ];
  for (const language of languages) {
    for (const [key, value] of Object.entries(catalog[language])) {
      if (!key.startsWith('rules_') || typeof value !== 'string') continue;
      if (forbiddenRuleTerms.some(pattern => pattern.test(value))) {
        fail(`data/i18n.json: ${language}.${key} contains a technical term in player-facing rules`);
      }
    }
  }
}

function checkReleaseMarkers() {
  const files = walk(root, file => /\.(py|js|json|html|css|md|ps1|yml|yaml|ini|mako)$/.test(file));
  const markerAllowlist = new Set(['QUALITY_GATES.md', 'scripts/static-checks.js']);
  const checks = [
    { pattern: /TODO_FIX/, message: 'contains TODO_FIX marker' },
    { pattern: /console\.log\(\s*['"`]debug/i, message: 'contains debug console.log marker' },
    { pattern: /\.on_event\(/, message: 'uses deprecated FastAPI on_event' },
    { pattern: /HTTP_422_UNPROCESSABLE_ENTITY/, message: 'uses deprecated HTTP_422_UNPROCESSABLE_ENTITY' },
  ];

  for (const filePath of files) {
    if (markerAllowlist.has(rel(filePath))) {
      continue;
    }
    const text = read(filePath);
    for (const check of checks) {
      if (check.pattern.test(text)) {
        fail(`${rel(filePath)}: ${check.message}`);
      }
    }
  }
}

function checkSecrets() {
  const files = walk(root, file => /\.(py|js|json|html|css|md|ps1|yml|yaml|ini|mako|example)$/.test(file));
  const allowlist = new Set([
    '.env.compose.example',
    'backend/.env.example',
    'backend/.env.production.example',
    'backend/README.md',
    'DEPLOYMENT.md',
    'RENDER_NEON_DEPLOY.md',
    'scripts/static-checks.js'
  ]);
  const checks = [
    { pattern: /\b\d{8,12}:[A-Za-z0-9_-]{30,}\b/, message: 'looks like a Telegram bot token' },
    { pattern: /\bsk-[A-Za-z0-9_-]{24,}\b/, message: 'looks like an API secret key' },
    { pattern: /\bAIza[0-9A-Za-z_-]{30,}\b/, message: 'looks like a Google API key' },
    { pattern: /-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----/, message: 'contains a private key' },
    { pattern: /client_secret\s*[:=]\s*["']?[A-Za-z0-9_-]{24,}/i, message: 'contains a real-looking OAuth client secret' },
  ];

  for (const filePath of files) {
    const relative = rel(filePath);
    if (allowlist.has(relative)) continue;
    const text = read(filePath);
    for (const check of checks) {
      if (check.pattern.test(text)) {
        fail(`${relative}: ${check.message}`);
      }
    }
  }
}

function hasMojibake(text) {
  const cp1251Byte80ToBF = new Set(Array.from(
    '\u0402\u0403\u201A\u0453\u201E\u2026\u2020\u2021\u20AC\u2030\u0409\u2039\u040A\u040C\u040B\u040F' +
    '\u0452\u2018\u2019\u201C\u201D\u2022\u2013\u2014\u2122\u0459\u203A\u045A\u045C\u045B\u045F' +
    '\u00A0\u040E\u045E\u0408\u00A4\u0490\u00A6\u00A7\u0401\u00A9\u0404\u00AB\u00AC\u00AD\u00AE\u0407' +
    '\u00B0\u00B1\u0406\u0456\u0491\u00B5\u00B6\u00B7\u0451\u2116\u0454\u00BB\u0458\u0405\u0455\u0457'
  ));
  const cp1251EmojiSecond = new Set(['\u045F', '\u040F']);
  const cp1252Second = new Set(['\u0402', '\u201A', '\u201E', '\u2026', '\u20AC', '\u2122', '\u045A', '\u045C']);

  for (let i = 0; i < text.length - 1; i += 1) {
    const current = text[i];
    const next = text[i + 1];
    if ((current === '\u0420' || current === '\u0421') && cp1251Byte80ToBF.has(next)) {
      return true;
    }
    if (current === '\u0440' && cp1251EmojiSecond.has(next)) {
      return true;
    }
    if (current === '\u0432' && cp1252Second.has(next)) {
      return true;
    }
  }

  return text.includes('\uFFFD') || /(^|[^?])\?{4,}([^?]|$)/.test(text);
}

function checkMojibake() {
  const files = walk(root, file => /\.(js|json|html|css|md|py|ps1|yml|yaml)$/.test(file));
  for (const filePath of files) {
    const text = read(filePath);
    if (hasMojibake(text)) {
      fail(`${rel(filePath)}: possible mojibake / broken text encoding`);
    }
  }
}

function checkBlankLinks() {
  const htmlFiles = [
    ...walk(root, file => file.endsWith('.html') && path.dirname(file) === root),
    ...walk(path.join(root, 'pages'), file => file.endsWith('.html')),
  ];
  const anchorPattern = /<a\b[^>]*target\s*=\s*["']_blank["'][^>]*>/gi;

  for (const filePath of htmlFiles) {
    const text = read(filePath);
    const matches = text.match(anchorPattern) || [];
    for (const anchor of matches) {
      const relMatch = anchor.match(/\brel\s*=\s*["']([^"']*)["']/i);
      const relTokens = new Set((relMatch ? relMatch[1] : '').toLowerCase().split(/\s+/).filter(Boolean));
      if (!relTokens.has('noreferrer') && !relTokens.has('noopener')) {
        fail(`${rel(filePath)}: target="_blank" link is missing rel="noopener noreferrer"`);
      }
    }
  }
}

function frontendHtmlFiles() {
  return [
    path.join(root, 'index.html'),
    ...walk(path.join(root, 'pages'), file => file.endsWith('.html')),
  ].filter(file => fs.existsSync(file));
}

function stripUrlSuffix(value) {
  return String(value || '').split('#')[0].split('?')[0];
}

function localReference(filePath, value) {
  const clean = stripUrlSuffix(value).trim();
  if (!clean || /[{}]/.test(clean) || /^(?:#|https?:|mailto:|tel:|data:|javascript:|about:)/i.test(clean)) return '';
  return clean.startsWith('/')
    ? path.resolve(root, clean.replace(/^\/+/, ''))
    : path.resolve(path.dirname(filePath), clean);
}

function checkFrontendContracts() {
  const htmlFiles = frontendHtmlFiles();
  const knownRoutes = new Set([
    'home', 'games', 'bonuses', 'vip', 'profile', 'admin', 'deposit', 'withdraw',
    'help', 'privacy', 'terms', 'responsible', 'dataGames', 'dataI18n', 'css'
  ]);
  const scriptConsumers = new Map();

  for (const filePath of htmlFiles) {
    const source = read(filePath);
    const relative = rel(filePath);
    if (relative.startsWith('pages/') && /js\/core\/bootstrap\.js(?:\?[^"']*)?["']/i.test(source)) {
      fail(`${relative}: internal page loads the home controller; use js/core/page-bootstrap.js`);
    }
    if (/\b(?:localhost|127\.0\.0\.1)(?::\d+)?\b/i.test(source)) {
      fail(`${relative}: public HTML contains a localhost URL`);
    }

    const ids = new Set();
    for (const match of source.matchAll(/\bid\s*=\s*["']([^"']+)["']/gi)) {
      if (ids.has(match[1])) fail(`${relative}: duplicate id="${match[1]}"`);
      ids.add(match[1]);
    }

    for (const match of source.matchAll(/\bdata-route\s*=\s*["']([^"']+)["']/gi)) {
      if (!knownRoutes.has(match[1])) fail(`${relative}: unknown data-route="${match[1]}"`);
    }

    for (const match of source.matchAll(/\b(?:href|src)\s*=\s*["']([^"']+)["']/gi)) {
      const value = match[1].trim();
      const resolved = localReference(filePath, value);
      if (resolved && !fs.existsSync(resolved)) {
        fail(`${relative}: local reference does not exist (${value})`);
      }
      if (value.startsWith('#') && value.length > 1 && !ids.has(value.slice(1))) {
        fail(`${relative}: fragment target does not exist (${value})`);
      }
    }

    for (const match of source.matchAll(/<script\b[^>]*\bsrc=["']([^"']+)["']/gi)) {
      const resolved = localReference(filePath, match[1]);
      if (!resolved || !/[/\\]js[/\\](?:pages|games)[/\\].+\.js$/i.test(resolved)) continue;
      const consumers = scriptConsumers.get(resolved) || [];
      consumers.push({ filePath, ids });
      scriptConsumers.set(resolved, consumers);
    }
  }

  for (const filePath of [
    ...walk(path.join(root, 'js', 'pages'), file => file.endsWith('.js')),
    ...walk(path.join(root, 'js', 'games'), file => file.endsWith('.js')),
  ]) {
    const source = read(filePath);
    if (/DOMContentLoaded/.test(source)) {
      fail(`${rel(filePath)}: page controller must be initialized by the shared bootstrap`);
    }
  }

  for (const filePath of walk(path.join(root, 'js', 'games'), file => file.endsWith('.js'))) {
    const source = read(filePath);
    if (!/\binitialized\s*=\s*false\b/.test(source) || !/\binitialized\b[\s\S]{0,120}\breturn\b/.test(source)) {
      fail(`${rel(filePath)}: game controller must guard against repeated initialization`);
    }
    if (/getContext\(\s*['"]2d['"]\s*\)/.test(source)) {
      if (!/\bdevicePixelRatio\b/.test(source)) {
        fail(`${rel(filePath)}: canvas controller must account for devicePixelRatio`);
      }
      if (!/\bResizeObserver\b/.test(source)) {
        fail(`${rel(filePath)}: canvas controller must react to element resize`);
      }
    }
  }

  // A controller used by exactly one page has a strict DOM contract. Shared
  // controllers intentionally contain optional elements for several pages.
  for (const [scriptPath, consumers] of scriptConsumers) {
    if (consumers.length !== 1 || !fs.existsSync(scriptPath)) continue;
    const scriptSource = read(scriptPath);
    const references = new Set();
    const generatedIds = new Set();
    for (const match of scriptSource.matchAll(/getElementById\(\s*["']([^"']+)["']\s*\)/g)) {
      references.add(match[1]);
    }
    for (const match of scriptSource.matchAll(/\bid=["']([^"']+)["']/g)) generatedIds.add(match[1]);
    for (const match of scriptSource.matchAll(/\.id\s*=\s*["']([^"']+)["']/g)) generatedIds.add(match[1]);
    for (const id of references) {
      if (!consumers[0].ids.has(id) && !generatedIds.has(id)) {
        fail(`${rel(scriptPath)}: expects #${id}, missing from ${rel(consumers[0].filePath)}`);
      }
    }
  }
}

function checkBukamikuLanguageNavigation() {
  const htmlPath = path.join(root, 'bukamiku_service', 'static', 'index.html');
  const cssPath = path.join(root, 'bukamiku_service', 'static', 'styles.css');
  const scriptPath = path.join(root, 'bukamiku_service', 'static', 'script.js');
  if (![htmlPath, cssPath, scriptPath].every(filePath => fs.existsSync(filePath))) return;

  const html = read(htmlPath);
  const css = read(cssPath);
  const script = read(scriptPath);
  const ids = new Set();
  for (const match of html.matchAll(/\bid\s*=\s*["']([^"']+)["']/gi)) {
    if (ids.has(match[1])) fail(`bukamiku_service/static/index.html: duplicate id="${match[1]}"`);
    ids.add(match[1]);
  }

  const switches = html.match(/class=["'][^"']*\blang-switch\b[^"']*["']/gi) || [];
  const ruButtons = html.match(/class=["'][^"']*\blang-btn\b[^"']*["'][^>]*data-lang=["']ru["']/gi) || [];
  const enButtons = html.match(/class=["'][^"']*\blang-btn\b[^"']*["'][^>]*data-lang=["']en["']/gi) || [];
  if (switches.length < 2 || ruButtons.length < 2 || enButtons.length < 2) {
    fail('bukamiku_service: desktop and mobile RU/EN language controls are required');
  }
  if (!css.includes('.header__right>.lang-switch{display:none}') || !css.includes('.lang-switch--drawer{display:flex}')) {
    fail('bukamiku_service: the mobile drawer language switch must remain visible at narrow widths');
  }
  for (const contract of ['document.documentElement.lang = lang', "btn.setAttribute('aria-pressed'", "btn.dataset.i18nReady === '1'"]) {
    if (!script.includes(contract)) fail(`bukamiku_service/static/script.js: missing language contract (${contract})`);
  }
}

function checkI18nSanitizerPath() {
  const uiPath = path.join(root, 'js', 'core', 'ui.js');
  const text = read(uiPath);
  if (!/function\s+sanitizeRichText\s*\(/.test(text)) {
    fail('js/core/ui.js: sanitizeRichText function is missing');
  }
  if (!/\[data-i18n-html\][\s\S]{0,180}innerHTML\s*=\s*sanitizeRichText\s*\(\s*t\s*\(/.test(text)) {
    fail('js/core/ui.js: data-i18n-html must render through sanitizeRichText(t(...))');
  }

  for (const filePath of walk(path.join(root, 'js'), file => file.endsWith('.js'))) {
    const source = read(filePath);
    const suspicious = source.match(/innerHTML\s*=\s*t\s*\(/);
    if (suspicious) {
      fail(`${rel(filePath)}: direct innerHTML = t(...) bypasses rich-text sanitizer`);
    }
  }
}

function checkPerformanceBudgets() {
  const maxImageBytes = 300 * 1024;
  const maxAssetImageBytes = 1024 * 1024;
  // style.css remains as a compatibility artifact, but pages must load the
  // modular core/page/game styles below instead of shipping every theme.
  const maxCssBytes = 320 * 1024;
  const maxPageCssBytes = 96 * 1024;
  const pageCssBudgetBytes = new Map();
  // Kawaui Studio adds a small shared identity/wallet client to authenticated pages.
  const maxPageScriptBytes = 440 * 1024;
  const pageScriptBudgetBytes = new Map([
    // Admin loads the shared account schema plus its own data-management modules.
    ['pages/admin.html', 484 * 1024],
  ]);
  const maxPageScripts = 8;
  const maxPageStylesheets = 3;

  const imageFiles = walk(path.join(root, 'assets'), file => /\.(png|jpe?g|gif|webp|avif)$/i.test(file));
  let assetImageBytes = 0;
  const imageHashes = new Map();
  for (const filePath of imageFiles) {
    const size = fs.statSync(filePath).size;
    assetImageBytes += size;
    if (size > maxImageBytes) {
      fail(`${rel(filePath)}: image is ${(size / 1024).toFixed(1)} KB; budget is ${maxImageBytes / 1024} KB`);
    }
    const hash = require('crypto').createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
    const duplicate = imageHashes.get(hash);
    if (duplicate) fail(`${rel(filePath)}: duplicates image content from ${rel(duplicate)}`);
    else imageHashes.set(hash, filePath);
  }
  if (assetImageBytes > maxAssetImageBytes) {
    fail(`assets: raster images total ${(assetImageBytes / 1024).toFixed(1)} KB; budget is ${maxAssetImageBytes / 1024} KB`);
  }

  for (const filePath of walk(path.join(root, 'css'), file => file.endsWith('.css'))) {
    const bytes = fs.readFileSync(filePath);
    const size = bytes.length;
    if (size > maxCssBytes) {
      fail(`${rel(filePath)}: stylesheet is ${(size / 1024).toFixed(1)} KB; budget is ${maxCssBytes / 1024} KB`);
    }
    if (path.basename(filePath) === 'style.css' && bytes.includes(13)) {
      fail(`${rel(filePath)}: generated stylesheet contains CR bytes; normalize CRLF/LF in scripts/build-css.js`);
    }
    if (/fonts\.googleapis\.com/i.test(read(filePath))) {
      fail(`${rel(filePath)}: external Google Fonts import blocks first render`);
    }
  }

  const htmlFiles = [
    ...walk(root, file => file.endsWith('.html') && path.dirname(file) === root),
    ...walk(path.join(root, 'pages'), file => file.endsWith('.html')),
  ];
  for (const filePath of htmlFiles) {
    const source = read(filePath);
    for (const match of source.matchAll(/<img\b[^>]*>/gi)) {
      const tag = match[0];
      if (!/\bdecoding=["']async["']/i.test(tag)) {
        fail(`${rel(filePath)}: every image must declare decoding="async"`);
      }
      if (!/\bloading=["'](?:lazy|eager)["']/i.test(tag)) {
        fail(`${rel(filePath)}: every image must explicitly declare loading="lazy" or loading="eager"`);
      }
    }
    if (/<nav\b[^>]*\bid=["']navbar["']/i.test(source) && /class=["'][^"']*nav-inner/i.test(source) && !/js\/core\/ui\.js(?:\?[^"']*)?["']/i.test(source)) {
      fail(`${rel(filePath)}: standard navbar requires js/core/ui.js for mobile navigation`);
    }
    const stylesheets = Array.from(source.matchAll(/<link\b[^>]*\brel=["']stylesheet["'][^>]*\bhref=["']([^"']+)["']/gi));
    const stylesheetHrefs = stylesheets.map(match => match[1].split('?')[0].replace(/\\/g, '/'));
    if (stylesheetHrefs.some(href => /(?:^|\/)css\/style\.css$/i.test(href))) {
      fail(`${rel(filePath)}: compatibility css/style.css must not be loaded by pages; use modular stylesheets`);
    }
    const gameThemes = stylesheetHrefs.filter(href => /(?:^|\/)css\/games\/(?!shared\.css$)[^/]+\.css$/i.test(href));
    if (gameThemes.length > 1) {
      fail(`${rel(filePath)}: loads multiple game themes (${gameThemes.join(', ')})`);
    }
    if (gameThemes.length === 1 && !stylesheetHrefs.some(href => /(?:^|\/)css\/games\/shared\.css$/i.test(href))) {
      fail(`${rel(filePath)}: game theme requires css/games/shared.css`);
    }
    if (stylesheets.length > maxPageStylesheets) {
      fail(`${rel(filePath)}: loads ${stylesheets.length} stylesheets; budget is ${maxPageStylesheets}`);
    }
    let cssBytes = 0;
    for (const match of stylesheets) {
      const href = match[1].split('?')[0];
      if (/^(?:https?:)?\/\//i.test(href)) continue;
      const resolved = path.resolve(path.dirname(filePath), href);
      if (fs.existsSync(resolved)) cssBytes += fs.statSync(resolved).size;
    }
    const cssBudget = pageCssBudgetBytes.get(rel(filePath)) || maxPageCssBytes;
    if (cssBytes > cssBudget) {
      fail(`${rel(filePath)}: raw stylesheet payload is ${(cssBytes / 1024).toFixed(1)} KB; budget is ${cssBudget / 1024} KB`);
    }
    const scripts = Array.from(source.matchAll(/<script\b[^>]*\bsrc=["']([^"']+)["']/gi));
    if (scripts.length > maxPageScripts) {
      fail(`${rel(filePath)}: loads ${scripts.length} scripts; budget is ${maxPageScripts}`);
    }
    let scriptBytes = 0;
    for (const match of scripts) {
      const src = match[1].split('?')[0];
      if (/^(?:https?:)?\/\//i.test(src)) continue;
      const resolved = path.resolve(path.dirname(filePath), src);
      if (fs.existsSync(resolved)) scriptBytes += fs.statSync(resolved).size;
    }
    const scriptBudget = pageScriptBudgetBytes.get(rel(filePath)) || maxPageScriptBytes;
    if (scriptBytes > scriptBudget) {
      fail(`${rel(filePath)}: raw script payload is ${(scriptBytes / 1024).toFixed(1)} KB; budget is ${scriptBudget / 1024} KB`);
    }
  }
}

checkJson();
checkI18nCoverage();
checkReleaseMarkers();
checkSecrets();
checkMojibake();
checkBlankLinks();
checkFrontendContracts();
checkBukamikuLanguageNavigation();
checkI18nSanitizerPath();
checkPerformanceBudgets();

if (failures.length) {
  console.error('Static checks failed:');
  for (const item of failures) {
    console.error(`- ${item}`);
  }
  process.exit(1);
}

console.log('Static checks passed');
