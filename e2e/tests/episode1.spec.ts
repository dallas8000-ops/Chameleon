import { expect, test, type Page } from "@playwright/test";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

// eslint-disable-next-line @typescript-eslint/no-require-imports
const ffprobe: string = require("ffprobe-static").path;
// eslint-disable-next-line @typescript-eslint/no-require-imports
const ffmpeg: string = require("ffmpeg-static");
const outDir = path.join(__dirname, "..", ".runtime", "artifacts");

// A short invented script in the series format: 9 scenes (hook, 7 lines, closer), like the Episode 1 shot list.
const SCRIPT = `### Ep 1 — "Arrival"
**Hook (on screen):** I moved to blend in.

**Scene: a busy street.**

HERO (to camera): Line two.
A child waves from a stall.
CHILD: Hello, stranger!
HERO: Line five.
GUIDE (laughing): Line six.
HERO: Line seven.
CHILD: Line eight.

**Closer:** Word of the day: Foreigner = outsider.
`;

// Shot list: [scene type, media, trim start, trim end or image seconds]; lengths sum to 35 s.
const SHOTS: [string, string, number, number][] = [
  ["image", "still.png", 0, 3],
  ["video", "clipA.mp4", 1, 7],
  ["video", "clipB.mp4", 0, 2],
  ["video", "clipA.mp4", 0, 3],
  ["video", "clipA.mp4", 2, 7],
  ["video", "clipS.mp4", 0, 6],
  ["video", "clipA.mp4", 0, 3],
  ["video", "clipB.mp4", 0, 4],
  ["image", "still.png", 0, 3],
];
const EXPECTED_SECONDS = 35;

function make(dir: string, name: string, ...args: string[]) {
  const target = path.join(dir, name);
  execFileSync(ffmpeg, ["-y", "-loglevel", "error", ...args, target]);
  return target;
}

function brightPixels(file: string, at: number, filter: string): number {
  const result = spawnSync(
    ffmpeg,
    ["-v", "error", "-ss", String(at), "-i", file, "-frames:v", "1", "-vf", `${filter},format=gray`, "-f", "rawvideo", "-"],
    { maxBuffer: 1 << 26 },
  );
  return [...result.stdout].filter((value) => value > 200).length;
}

function meanVolume(file: string, from: number, length: number): number {
  const result = spawnSync(
    ffmpeg,
    ["-v", "info", "-ss", String(from), "-t", String(length), "-i", file, "-af", "volumedetect", "-f", "null", "-"],
    { encoding: "utf8" },
  );
  const match = /mean_volume: (-?[\d.]+|-inf) dB/.exec(result.stderr);
  if (!match) throw new Error("volumedetect produced no result");
  return match[1] === "-inf" ? -120 : Number(match[1]);
}

async function exportAndDownload(page: Page, name: string): Promise<string> {
  await page.getByRole("button", { name: "Queue export", exact: true }).click();
  // Eager Celery in the e2e backend renders inside the POST, so allow for the full render here.
  await expect(page.getByText(/Export status:/)).toBeVisible({ timeout: 120_000 });
  await expect(async () => {
    await page.getByRole("button", { name: "Refresh status" }).click();
    await expect(page.getByText("Export status: completed")).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 90_000, intervals: [1_000] });
  const href = await page.getByRole("link", { name: "Download video" }).getAttribute("href");
  const response = await page.request.get(href!);
  expect(response.ok()).toBeTruthy();
  mkdirSync(outDir, { recursive: true });
  const file = path.join(outDir, name);
  writeFileSync(file, await response.body());
  return file;
}

test("Episode 1 is built from a script with trims, overlays, a voice track and an AI label, then exported", async ({ page }) => {
  test.setTimeout(300_000);
  const dir = mkdtempSync(path.join(os.tmpdir(), "chameleon-ep1-"));
  make(dir, "clipA.mp4", "-f", "lavfi", "-i", "color=c=0x102040:s=640x360:d=8:r=25", "-f", "lavfi", "-i", "sine=frequency=300:duration=8", "-shortest", "-pix_fmt", "yuv420p");
  make(dir, "clipB.mp4", "-f", "lavfi", "-i", "color=c=0x203020:s=640x360:d=5:r=25", "-f", "lavfi", "-i", "sine=frequency=500:duration=5", "-shortest", "-pix_fmt", "yuv420p");
  make(dir, "clipS.mp4", "-f", "lavfi", "-i", "color=c=0x302010:s=640x360:d=8:r=25", "-an", "-pix_fmt", "yuv420p");
  make(dir, "still.png", "-f", "lavfi", "-i", "color=c=0x101830:s=320x180", "-frames:v", "1");
  make(dir, "kato-line.wav", "-f", "lavfi", "-i", "sine=frequency=800:duration=3");

  await page.goto("/register");
  await page.getByLabel(/email/i).fill(`ep1-${Date.now()}@example.com`);
  await page.getByLabel(/password/i).fill("Zq7!pleasant-Harbor-42");
  await page.getByLabel(/workspace name/i).fill("Muzungu Test");
  await page.getByRole("button", { name: /create workspace/i }).click();
  await expect(page).toHaveURL(/\/app$/);

  // Script import: one project, nine scenes.
  await page.getByRole("link", { name: "Import script" }).first().click();
  await page.getByLabel("Script", { exact: true }).fill(SCRIPT);
  await page.getByRole("button", { name: "Preview import" }).click();
  await expect(page.getByText("9 scenes")).toBeVisible();
  await page.getByRole("button", { name: /^Import 1 episode$/ }).click();
  await page.getByRole("link", { name: "Ep 1: Arrival" }).click();
  await expect(page.getByRole("heading", { name: /Studio: Ep 1: Arrival/ })).toBeVisible();

  // Upload the stand-in media and the voice line.
  for (const file of ["clipA.mp4", "clipB.mp4", "clipS.mp4", "still.png", "kato-line.wav"]) {
    await page.getByLabel("Upload media").setInputFiles(path.join(dir, file));
    await page.getByRole("button", { name: "Upload asset" }).click();
    await expect(page.getByText(file, { exact: true })).toBeVisible();
  }

  // Build each shot through the scene details panel.
  for (const [index, [type, media, from, to]] of SHOTS.entries()) {
    const number = index + 1;
    await page.getByRole("button", { name: new RegExp(`^#${number}\\b`) }).click();
    await expect(page.getByRole("heading", { name: `Scene ${number} details` })).toBeVisible();
    await page.getByLabel("Scene type").selectOption(type);
    await page.getByLabel("Media for this scene").selectOption({ label: media });
    if (type === "image") {
      await page.getByLabel("Show for (seconds)").fill(String(to));
    } else {
      await page.getByLabel("Trim start (seconds)").fill(String(from));
      await page.getByLabel("Trim end (seconds)").fill(String(to));
    }
    if (number === 1 || number === 9) {
      await page.getByRole("button", { name: "Add text overlay" }).click();
      await page.getByLabel("Overlay 1 text").fill(number === 1 ? "I moved to blend in." : "Foreigner = outsider");
      await page.getByLabel("Overlay 1 end").fill("2.5");
      await page.getByLabel("Overlay 1 size").selectOption("large");
    }
    if (number === 6) {
      await page.getByLabel("Voice track audio").selectOption({ label: "kato-line.wav" });
      await page.getByLabel("Voice starts at (seconds)").fill("0.5");
    }
    await page.getByRole("button", { name: "Save scene" }).click();
    await expect(page.getByText("Scene saved.")).toBeVisible();
  }

  // Mark the project as containing AI-generated people, then export without and with the label.
  await page.getByLabel("This project contains AI-generated people").click();
  await expect(page.getByLabel("This project contains AI-generated people")).toBeChecked();
  await page.getByRole("link", { name: "Go to export" }).click();
  await expect(page.getByText("Before you post: AI disclosure")).toBeVisible();
  const plain = await exportAndDownload(page, "ep1-plain.mp4");
  await page.getByLabel(/Add a small AI-generated label/).check();
  const labelled = await exportAndDownload(page, "ep1-labelled.mp4");

  // Format, codecs and total length.
  const probe = JSON.parse(execFileSync(ffprobe, [
    "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,width,height", "-of", "json", plain,
  ]).toString());
  const video = probe.streams.find((s: { codec_type: string }) => s.codec_type === "video");
  const audio = probe.streams.find((s: { codec_type: string }) => s.codec_type === "audio");
  expect([video.width, video.height, video.codec_name]).toEqual([1080, 1920, "h264"]);
  expect(audio.codec_name).toBe("aac");
  expect(Math.abs(Number(probe.format.duration) - EXPECTED_SECONDS)).toBeLessThan(0.6);
  const decode = spawnSync(ffmpeg, ["-v", "error", "-i", plain, "-f", "null", "-"], { encoding: "utf8" });
  expect(decode.status).toBe(0);
  expect(decode.stderr.trim()).toBe("");

  // The hook text and the end card are really on screen; ordinary shots have no text.
  const half = "scale=270:480";
  expect(brightPixels(plain, 1.0, half)).toBeGreaterThan(150);
  expect(brightPixels(plain, 33.0, half)).toBeGreaterThan(150);
  expect(brightPixels(plain, 10.0, half)).toBeLessThan(20);

  // Kato's voice line is audible over shot 6, whose own clip is silent.
  const shot6 = 3 + 6 + 2 + 3 + 5;
  expect(meanVolume(plain, shot6 + 0.7, 2.5)).toBeGreaterThan(-40);
  expect(meanVolume(plain, shot6 + 4.2, 1.5)).toBeLessThan(-60);

  // The AI label appears only in the labelled export.
  const strip = "crop=iw:ih*0.08:0:0,scale=540:154";
  expect(brightPixels(labelled, 10.0, strip)).toBeGreaterThan(15);
  expect(brightPixels(plain, 10.0, strip)).toBeLessThan(3);
});
