#!/usr/bin/env node
import { chromium } from 'playwright';
import fs from 'fs/promises';
import path from 'path';

const today = new Date().toISOString().slice(0, 10);
const base = (process.env.SCHOOLNET_BASE_URL || 'http://localhost:8006').replace(/\/$/, '');
const username = process.env.SCHOOLNET_USER || 'admin';
const password = process.env.SCHOOLNET_PASS || 'Demo1234';
const outDir = process.env.SCHOOLNET_CAPTURE_DIR || `reports/schoolnet-ui-${today}-auth`;

const publicRoutes = [
  '/',
  '/schools',
  '/register',
  '/login',
  '/admin/login',
];

const adminRoutes = [
  '/admin',
  '/admin/people',
  '/admin/roles',
  '/admin/permissions',
  '/admin/settings',
  '/admin/scheduler',
  '/admin/audit',
  '/admin/notifications',
  '/admin/file-uploads',
  '/admin/schools',
  '/admin/billing/products',
  '/admin/billing/prices',
  '/admin/billing/customers',
  '/admin/billing/subscriptions',
  '/admin/billing/invoices',
  '/admin/billing/payment-methods',
  '/admin/billing/coupons',
  '/admin/billing/entitlements',
  '/admin/billing/webhook-events',
];

function routeToFilename(route) {
  return route === '/' ? 'home' : route.replace(/^\//, '').replace(/\//g, '-');
}

async function captureRoute(page, route) {
  const url = `${base}${route}`;
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.waitForTimeout(700);
  const name = routeToFilename(route);
  await page.screenshot({ path: path.join(outDir, `${name}.png`), fullPage: true });
  return name;
}

async function authenticate(page) {
  await page.goto(`${base}/admin/login`, { waitUntil: 'domcontentloaded', timeout: 20000 });

  const hasUsername = await page.locator('input[name="username"]').count();
  const hasPassword = await page.locator('input[name="password"]').count();
  if (!hasUsername || !hasPassword) {
    throw new Error('Expected /admin/login form fields were not found (username/password). Check SCHOOLNET_BASE_URL.');
  }

  await page.fill('input[name="username"]', username);
  await page.fill('input[name="password"]', password);
  await page.click('button[type="submit"]');
  await page.waitForTimeout(1500);

  const currentUrl = page.url();
  const pageText = await page.locator('body').innerText();
  if (currentUrl.includes('/admin/login') || /invalid username or password/i.test(pageText)) {
    throw new Error(`Login failed for user '${username}'. Still at ${currentUrl}`);
  }

  await page.goto(`${base}/admin`, { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.waitForTimeout(800);
  if (page.url().includes('/admin/login')) {
    throw new Error('Auth check failed: /admin redirected back to /admin/login');
  }
}

async function main() {
  await fs.mkdir(outDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
  const page = await context.newPage();

  let captured = 0;
  let failed = 0;

  console.log(`Base URL: ${base}`);
  console.log(`Output:   ${outDir}`);

  for (const route of publicRoutes) {
    try {
      const name = await captureRoute(page, route);
      console.log(`OK      ${route} -> ${name}.png`);
      captured += 1;
    } catch (err) {
      console.error(`FAIL    ${route} -> ${err.message}`);
      failed += 1;
    }
  }

  console.log('\n--- Auth step ---');
  try {
    await authenticate(page);
    console.log('AUTH OK  authenticated admin session established');
  } catch (err) {
    console.error(`AUTH FAIL  ${err.message}`);
    await browser.close();
    process.exit(1);
  }

  console.log('\n--- Admin route capture ---');
  for (const route of adminRoutes) {
    try {
      await page.goto(`${base}${route}`, { waitUntil: 'domcontentloaded', timeout: 20000 });
      await page.waitForTimeout(700);
      if (page.url().includes('/admin/login')) {
        console.error(`REDIRECT ${route} -> /admin/login`);
        failed += 1;
        continue;
      }
      const name = routeToFilename(route);
      await page.screenshot({ path: path.join(outDir, `${name}.png`), fullPage: true });
      console.log(`OK      ${route} -> ${name}.png`);
      captured += 1;
    } catch (err) {
      console.error(`FAIL    ${route} -> ${err.message}`);
      failed += 1;
    }
  }

  await browser.close();

  console.log('\n--- Summary ---');
  console.log(`Captured: ${captured}`);
  console.log(`Failed:   ${failed}`);
  console.log(`Output:   ${outDir}/`);

  if (failed > 0) process.exit(1);
}

main().catch((err) => {
  console.error(`FATAL   ${err.message}`);
  process.exit(1);
});
