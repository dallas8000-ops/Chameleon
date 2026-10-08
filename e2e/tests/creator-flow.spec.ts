import { expect, test, type Page } from "@playwright/test";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { deflateSync } from "node:zlib";

// eslint-disable-next-line @typescript-eslint/no-require-imports
const ffprobe: string = require("ffprobe-static").path;
// eslint-disable-next-line @typescript-eslint/no-require-imports
const ffmpeg: string = require("ffmpeg-static");
const outDir = path.join(__dirname, "..", ".runtime", "artifacts");

// Minimal valid RGB PNG, generated locally (no external downloads).
function png(width: number, height: number): Buffer {
  const crc = (buf: Buffer) => {
    let c, crcVal = 0xffffffff;
    for (const byte of buf) {
      c = (crcVal ^ byte) & 0xff;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      crcVal = (crcVal >>> 8) ^ c;
    }
    return (crcVal ^ 0xffffffff) >>> 0;
  };
  const chunk = (type: string, data: Buffer) => {
    const head = Buffer.alloc(4);
    head.writeUInt32BE(data.length);
    const body = Buffer.concat([Buffer.from(type), data]);
    const tail = Buffer.alloc(4);
    tail.writeUInt32BE(crc(body));
    return Buffer.concat([head, body, tail]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;
  ihdr[9] = 2;
  const row = Buffer.concat([Buffer.from([0]), Buffer.alloc(width * 3, 0x7f)]);
  const raw = Buffer.concat(Array.from({ length: height }, () => row));
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr), chunk("IDAT", deflateSync(raw)), chunk("IEND", Buffer.alloc(0)),
  ]);
}

async function csrf(page: Page): Promise<string> {
  const response = await page.request.get("/api/auth/csrf/");
  return (await response.json()).csrfToken;
}

test("creator registers, uploads, edits captions, and exports a real MP4", async ({ page, browser, baseURL }) => {
  const email = `creator-${Date.now()}-${Math.random().toString(16).slice(2, 8)}@example.com`;
  const password = "Zq7!pleasant-Harbor-42";
  const providerWrites: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (request.method() !== "GET" && /\/api\/jobs\//.test(url.pathname)) providerWrites.push(url.pathname);
    // The browser must only talk to the local origin.
    expect(url.hostname).toBe("127.0.0.1");
  });

  // Registration through the real UI.
  await page.goto("/");
  await page.getByRole("link", { name: /get started/i }).click();
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill(password);
  await page.getByLabel(/workspace name/i).fill("Creator Studio");
  await page.getByRole("button", { name: /create workspace/i }).click();
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByRole("heading", { name: "Creator Studio" })).toBeVisible();

  // Session persists across a reload, then login works after the session is dropped.
  await page.reload();
  await expect(page.getByRole("heading", { name: "Creator Studio" })).toBeVisible();
  await page.context().clearCookies();
  await page.goto("/app");
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/app$/);

  // Project creation.
  await page.getByLabel("Project title").fill("Launch teaser");
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page).toHaveURL(/\/app\/projects\/\d+\/studio$/);
  await expect(page.getByRole("heading", { name: /Studio: Launch teaser/ })).toBeVisible();
  const projectId = page.url().match(/projects\/(\d+)\//)![1];

  // Generation is gated and presenter generation unavailable; no paid request is possible.
  await expect(page.getByText(/Cost estimate unavailable/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Generate image", exact: true })).toBeDisabled();
  await expect(page.getByText(/Presenter generation is unavailable/)).toBeVisible();
  const capabilities = await (await page.request.get("/api/jobs/capabilities/?workspace_id=1")).json();
  const image = capabilities.capabilities.find((item: { capability: string }) => item.capability === "image.generate");
  expect(image.can_submit).toBe(false);

  // Private image upload and picker.
  await page.getByLabel("Upload media").setInputFiles({ name: "frame.png", mimeType: "image/png", buffer: png(320, 180) });
  await page.getByRole("button", { name: "Upload asset" }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "frame.png" })).toBeVisible();

  await page.getByLabel("Scene title").fill("Opening frame");
  await page.getByLabel("Scene kind").selectOption("image");
  await page.getByRole("combobox", { name: /Media asset/ }).selectOption({ label: /frame\.png/ } as never).catch(async () => {
    const value = await page.getByRole("combobox", { name: /Media asset/ }).locator("option", { hasText: "frame.png" }).getAttribute("value");
    await page.getByRole("combobox", { name: /Media asset/ }).selectOption(value!);
  });
  await page.getByLabel(/Duration/).fill("2");
  await page.getByRole("button", { name: "Add scene", exact: true }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "Opening frame (image)" })).toBeVisible();

  // Reload: the scene and its asset/duration config must come from the server, not client state.
  await page.reload();
  await expect(page.getByRole("listitem").filter({ hasText: "Opening frame (image)" })).toBeVisible();
  const assets = await (await page.request.get("/api/assets/?workspace_id=1")).json();
  const assetList = (assets.results ?? assets) as { id: number; name: string }[];
  const frame = assetList.find((item) => item.name === "frame.png")!;
  expect(frame).toBeTruthy();
  const persisted = await (await page.request.get(`/api/projects/${projectId}/`)).json();
  expect(persisted.scenes).toHaveLength(1);
  expect(persisted.scenes[0].title).toBe("Opening frame");
  expect(persisted.scenes[0].config).toMatchObject({ asset_id: frame.id, duration_seconds: 2 });

  // Captions entirely through the UI: create the track, add a segment, validate, save, reload.
  await page.getByRole("button", { name: "Create caption track" }).click();
  await expect(page.getByRole("heading", { name: /Captions \(en\)/ })).toBeVisible();
  await page.getByRole("button", { name: "Add segment" }).click();
  await page.getByRole("button", { name: "Save captions" }).click();
  await expect(page.getByRole("alert").filter({ hasText: /Segment 1 text is required/ })).toBeVisible();
  await page.getByLabel("Segment 1 text").fill("Hello draft");
  await page.getByRole("button", { name: "Add segment" }).click();
  await page.getByLabel("Segment 2 text").fill("Throwaway");
  await page.getByRole("button", { name: "Remove segment 2" }).click();
  await expect(page.getByLabel("Segment 2 text")).toHaveCount(0);
  await page.getByLabel("Segment 1 end").fill("1.5");
  await page.getByLabel("Segment 1 text").fill("Hello Chameleon");
  await page.getByRole("button", { name: "Save captions" }).click();
  await expect(page.getByText("Captions saved.")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Segment 1 text")).toHaveValue("Hello Chameleon");
  await expect(page.getByLabel("Segment 2 text")).toHaveCount(0);
  // Export: queue, status, download.
  await page.getByRole("link", { name: "Go to export" }).click();
  await page.getByRole("button", { name: "Queue export", exact: true }).click();
  await expect(page.getByText(/Export status:/)).toBeVisible();
  await expect(async () => {
    await page.getByRole("button", { name: "Refresh status" }).click();
    await expect(page.getByText("Export status: completed")).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 90_000, intervals: [1_000] });
  const videoHref = await page.getByRole("link", { name: "Download video" }).getAttribute("href");
  const subtitleHref = await page.getByRole("link", { name: "Download subtitles" }).getAttribute("href");

  const video = await page.request.get(videoHref!);
  expect(video.ok()).toBeTruthy();
  const subtitles = await page.request.get(subtitleHref!);
  expect(await subtitles.text()).toContain("Hello Chameleon");

  mkdirSync(outDir, { recursive: true });
  const file = path.join(outDir, "export.mp4");
  writeFileSync(file, await video.body());
  const probe = JSON.parse(execFileSync(ffprobe, [
    "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,width,height",
    "-of", "json", file,
  ]).toString());
  const v = probe.streams.find((s: { codec_type: string }) => s.codec_type === "video");
  expect(v.codec_name).toBe("h264");
  const a = probe.streams.find((s: { codec_type: string }) => s.codec_type === "audio");
  expect(a?.codec_name).toBe("aac");
  expect([v.width, v.height]).toEqual([1080, 1920]);
  expect(Number(probe.format.duration)).toBeGreaterThan(1.5);
  expect(Number(probe.format.duration)).toBeLessThan(3);
  writeFileSync(path.join(outDir, "ffprobe.json"), JSON.stringify(probe, null, 2));

  // Full decode of every frame/sample of the downloaded file: execFileSync throws on non-zero exit,
  // and -v error means any decode problem is printed to stderr.
  const decode = spawnSync(ffmpeg, ["-v", "error", "-i", file, "-f", "null", "-"], { encoding: "utf8" });
  expect(decode.status).toBe(0);
  expect(decode.stderr.trim()).toBe("");

  // A second registered user must not reach the first user's private data.
  const exportId = videoHref!.match(/exports\/(\d+)\//)![1];
  const other = await browser.newContext({ baseURL });
  const otherPage = await other.newPage();
  await otherPage.goto("/register");
  await otherPage.getByLabel(/email/i).fill(`other-${Date.now()}@example.com`);
  await otherPage.getByLabel(/password/i).fill(password);
  await otherPage.getByLabel(/workspace name/i).fill("Other Studio");
  await otherPage.getByRole("button", { name: /create workspace/i }).click();
  await expect(otherPage).toHaveURL(/\/app$/);
  const forbidden = [
    `/api/assets/${frame.id}/`,
    `/api/projects/${projectId}/`,
    `/api/exports/${exportId}/`,
    videoHref!,
    subtitleHref!,
    "/api/assets/?workspace_id=1",
    "/api/projects/?workspace_id=1",
  ];
  for (const url of forbidden) {
    const response = await otherPage.request.get(url);
    const body = await response.text();
    const denied = [403, 404].includes(response.status())
      || (response.status() === 200 && /"results":\s*\[\s*\]|^\[\s*\]$/.test(body));
    expect(denied, `${url} -> ${response.status()}`).toBe(true);
    expect(body).not.toMatch(/frame\.png|Launch teaser|Hello Chameleon|Opening frame/);
  }
  await other.close();

  expect(providerWrites).toEqual([]);
});



