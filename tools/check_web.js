// 校验前端 DOM 引用与静态资源是否存在 (node tools/check_web.js)
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "web/index.html"), "utf8");
const js = fs.readFileSync(path.join(root, "web/app.js"), "utf8");
const css = fs.readFileSync(path.join(root, "web/styles.css"), "utf8");

const ids = new Set([
  ...html.matchAll(/id="([^"]+)"/g),
  ...js.matchAll(/id=\\?"([^"$]+)\\?"/g),      // 由 JS 动态插入的元素
].map((m) => m[1]));
const used = new Set([...js.matchAll(/\$\("([^"]+)"\)/g)].map((m) => m[1]));
const missing = [...used].filter((u) => !ids.has(u));

const classesInJs = new Set(
  [...js.matchAll(/className = [`"]([^`"]+)[`"]/g)]
    .flatMap((m) => m[1].split(/\s+/))
    .filter((c) => c && !c.includes("$"))
);
const htmlClasses = new Set([...html.matchAll(/class="([^"]+)"/g)].flatMap((m) => m[1].split(/\s+/)));
const cssClasses = new Set([...css.matchAll(/\.([a-zA-Z][\w-]*)/g)].map((m) => m[1]));
const undefinedClasses = [...classesInJs].filter((c) => c && !cssClasses.has(c) && !htmlClasses.has(c));

const rootTags = (html.match(/<html/g) || []).length;
const closeTags = (html.match(/<\/html>/g) || []).length;

console.log("html ids        :", ids.size);
console.log("js id refs      :", used.size, "| missing:", missing.length ? missing : "none");
console.log("js classes      :", classesInJs.size, "| no css rule:", undefinedClasses.length ? undefinedClasses : "none");
console.log("html tag balance:", rootTags === 1 && closeTags === 1 ? "ok" : "check");
process.exit(missing.length ? 1 : 0);
