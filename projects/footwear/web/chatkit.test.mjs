import { test } from "node:test";
import assert from "node:assert";
import { buildWidgetUrl } from "./chatkit.js";

test("buildWidgetUrl only includes params the widget declares", () => {
  const desc = {
    rest_path: "/api/v1/reports/footwear/product-mix",
    params: [{ name: "flow", type: "enum" }],
  };
  const url = buildWidgetUrl(desc, { flow: "IMPORT", heading: "64", months: 24 });
  assert.strictEqual(url, "/api/v1/reports/footwear/product-mix?flow=IMPORT");
});

test("buildWidgetUrl applies defaults for missing values", () => {
  const desc = {
    rest_path: "/x",
    params: [{ name: "months", type: "int", default: 24 }],
  };
  assert.strictEqual(buildWidgetUrl(desc, {}), "/x?months=24");
});

test("buildWidgetUrl prefixes basePath when rest_path is relative", () => {
  const desc = { rest_path: "reports/x", params: [] };
  assert.strictEqual(buildWidgetUrl(desc, {}, "/api/v1/"), "/api/v1/reports/x");
});

test("countries widget: flow + heading + top_n default", () => {
  const desc = {
    rest_path: "/api/v1/reports/footwear/countries",
    params: [
      { name: "flow", type: "enum", required: true },
      { name: "heading", type: "str" },
      { name: "top_n", type: "int", default: 10 },
    ],
  };
  const url = buildWidgetUrl(desc, { flow: "EXPORT", heading: "6403" });
  assert.strictEqual(
    url,
    "/api/v1/reports/footwear/countries?flow=EXPORT&heading=6403&top_n=10",
  );
});

test("balance widget: heading + months, no flow even if present in values", () => {
  const desc = {
    rest_path: "/api/v1/reports/footwear/balance",
    params: [
      { name: "heading", type: "str" },
      { name: "months", type: "int", default: 24 },
    ],
  };
  const url = buildWidgetUrl(desc, { flow: "IMPORT", heading: "64", months: 12 });
  assert.strictEqual(url, "/api/v1/reports/footwear/balance?heading=64&months=12");
});

test("evolution widget: flow + heading + months", () => {
  const desc = {
    rest_path: "/api/v1/reports/footwear/evolution",
    params: [
      { name: "flow", type: "enum" },
      { name: "heading", type: "str" },
      { name: "months", type: "int", default: 24 },
    ],
  };
  const url = buildWidgetUrl(desc, { flow: "IMPORT", heading: "64", months: 24 });
  assert.strictEqual(
    url,
    "/api/v1/reports/footwear/evolution?flow=IMPORT&heading=64&months=24",
  );
});

test("buildWidgetUrl skips empty-string values with no default", () => {
  const desc = {
    rest_path: "/x",
    params: [
      { name: "heading", type: "str" },
      { name: "flow", type: "enum" },
    ],
  };
  assert.strictEqual(buildWidgetUrl(desc, { heading: "", flow: "IMPORT" }), "/x?flow=IMPORT");
});
