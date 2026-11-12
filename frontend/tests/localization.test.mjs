import assert from "node:assert/strict";
import { test } from "node:test";
import { resolveLocale, translate, translateError } from "../src/locale.ts";
import { translatePoseText } from "../src/pose-copy.ts";

test("the saved choice takes priority and Chinese browser locales default to Simplified Chinese", () => {
  assert.equal(resolveLocale("en", ["zh-CN"]), "en");
  assert.equal(resolveLocale("zh-CN", ["en-US"]), "zh-CN");
  assert.equal(resolveLocale("bad-value", ["zh-Hans-CN", "en"]), "zh-CN");
  assert.equal(resolveLocale(null, ["en-US", "zh-CN"]), "en");
  assert.equal(resolveLocale(null, []), "en");
});

test("translated labels preserve stable API values and existing free text", () => {
  assert.equal(translate("zh-CN", "Character design sketch"), "角色设计草稿");
  assert.equal(translate("en", "Character design sketch"), "Character design sketch");
  assert.equal(translate("zh-CN", "A user's painting"), "A user's painting");
});

test("counted labels and HTTP fallbacks interpolate in the chosen language", () => {
  assert.equal(translate("zh-CN", "{count} priorities for the next pass", { count: 3 }), "下一轮修改的 3 个重点");
  assert.equal(translate("en", "Request failed ({status})", { status: 503 }), "Request failed (503)");
  assert.equal(translate("zh-CN", "Request failed ({status})", { status: 503 }), "请求失败（503）");
  assert.equal(translateError("zh-CN", "Images must be 10 MB or smaller."), "图片大小不能超过 10 MB。");
  assert.equal(translateError("zh-CN", "Daily AI limit reached (5). It resets at 00:00 UTC."), "今日 AI 调用已达上限（5 次），将在 UTC 00:00 重置。");
});


test("2D findings translate without rounding measurements or rewriting unknown provider messages", () => {
  assert.equal(translatePoseText("zh-CN", "Only 8 of 17 points are available."), "17 个关节点中只有 8 个可用。");
  assert.equal(translatePoseText("zh-CN", "Broad 2D tolerance under this style: 0.48–1.62"), "当前画风的宽松二维容差：0.48–1.62");
  assert.equal(translatePoseText("zh-CN", "Low-confidence points: left_ankle, right_wrist"), "低置信度关节点：左踝、右腕");
  assert.equal(translatePoseText("en", "Left Elbow bend differs from the reference"), "Left Elbow bend differs from the reference");
  assert.equal(translatePoseText("zh-CN", "An unknown worker warning"), "An unknown worker warning");
});
