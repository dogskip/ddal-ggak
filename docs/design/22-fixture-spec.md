# Fixture Repository 명세

> `fixtures/repos/react-vite-ts/` 실제 파일 내용.
> E2E/Integration 테스트에서 딸깍이 코드를 생성·검증할 기준 레포.

---

## 디렉토리 구조

```
fixtures/repos/react-vite-ts/
├── package.json
├── pnpm-lock.yaml          (pnpm install 후 자동 생성)
├── vite.config.ts
├── tsconfig.json
├── tsconfig.node.json
├── .eslintrc.cjs
├── index.html
├── public/
│   └── vite.svg
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── App.css
    ├── index.css
    └── assets/
        └── react.svg
```

---

## `package.json`

```json
{
  "name": "react-vite-ts-fixture",
  "private": true,
  "version": "0.0.1",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "lint": "eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@typescript-eslint/eslint-plugin": "^7.13.1",
    "@typescript-eslint/parser": "^7.13.1",
    "@vitejs/plugin-react": "^4.3.1",
    "eslint": "^8.57.0",
    "eslint-plugin-react-hooks": "^4.6.2",
    "eslint-plugin-react-refresh": "^0.4.7",
    "typescript": "^5.2.2",
    "vite": "^5.3.1"
  }
}
```

---

## `vite.config.ts`

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
```

---

## `tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

---

## `tsconfig.node.json`

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

---

## `.eslintrc.cjs`

```javascript
module.exports = {
  root: true,
  env: { browser: true, es2020: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  ignorePatterns: ['dist', '.eslintrc.cjs'],
  parser: '@typescript-eslint/parser',
  plugins: ['react-refresh'],
  rules: {
    'react-refresh/only-export-components': [
      'warn',
      { allowConstantExport: true },
    ],
  },
}
```

---

## `index.html`

```html
<!doctype html>
<html lang="ko">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Vite + React</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

---

## `src/main.tsx`

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

---

## `src/App.tsx` (딸깍 생성 대상)

```tsx
import { useState } from 'react'
import reactLogo from './assets/react.svg'
import viteLogo from '/vite.svg'
import './App.css'

function App() {
  const [count, setCount] = useState(0)

  return (
    <>
      <div>
        <a href="https://vitejs.dev" target="_blank">
          <img src={viteLogo} className="logo" alt="Vite logo" />
        </a>
        <a href="https://react.dev" target="_blank">
          <img src={reactLogo} className="logo react" alt="React logo" />
        </a>
      </div>
      <h1>Vite + React</h1>
      <div className="card">
        <button onClick={() => setCount((count) => count + 1)}>
          count is {count}
        </button>
        <p>
          Edit <code>src/App.tsx</code> and save to test HMR
        </p>
      </div>
      <p className="read-the-docs">
        Click on the Vite and React logos to learn more
      </p>
    </>
  )
}

export default App
```

---

## `src/App.css`

```css
#root {
  max-width: 1280px;
  margin: 0 auto;
  padding: 2rem;
  text-align: center;
}

.logo {
  height: 6em;
  padding: 1.5em;
  will-change: filter;
  transition: filter 300ms;
}
.logo:hover {
  filter: drop-shadow(0 0 2em #646cffaa);
}
.logo.react:hover {
  filter: drop-shadow(0 0 2em #61dafbaa);
}

@keyframes logo-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: no-preference) {
  a:nth-of-type(2) .logo {
    animation: logo-spin infinite 20s linear;
  }
}

.card {
  padding: 2em;
}

.read-the-docs {
  color: #888;
}
```

---

## `src/index.css`

```css
:root {
  font-family: Inter, system-ui, Avast, Helvetica, Arial, sans-serif;
  line-height: 1.5;
  font-weight: 400;
  color-scheme: light dark;
  color: rgba(255, 255, 255, 0.87);
  background-color: #242424;
}

a {
  font-weight: 500;
  color: #646cff;
  text-decoration: inherit;
}
a:hover { color: #535bf2; }

body {
  margin: 0;
  display: flex;
  place-items: center;
  min-width: 320px;
  min-height: 100vh;
}

h1 { font-size: 3.2em; line-height: 1.1; }

button {
  border-radius: 8px;
  border: 1px solid transparent;
  padding: 0.6em 1.2em;
  font-size: 1em;
  font-weight: 500;
  font-family: inherit;
  background-color: #1a1a1a;
  cursor: pointer;
  transition: border-color 0.25s;
}
button:hover { border-color: #646cff; }
button:focus, button:focus-visible { outline: 4px auto -webkit-focus-ring-color; }

@media (prefers-color-scheme: light) {
  :root {
    color: #213547;
    background-color: #ffffff;
  }
  a:hover { color: #747bff; }
  button { background-color: #f9f9f9; }
}
```

---

## 주의사항

### pnpm-lock.yaml 생성 방법
```bash
cd fixtures/repos/react-vite-ts
pnpm install
```
lock 파일은 `git add`에 포함해야 `--frozen-lockfile` CI 빌드가 성공한다.

### 딸깍 테스트에서의 역할

| 테스트 유형 | 픽스처 사용 방식 |
|-----------|--------------|
| integration/test_sandbox.py | repo_path로 직접 사용, worktree 생성 |
| integration/test_runtime_validator.py | sandbox 위에서 build/type/lint 실행 |
| e2e/test_full_loop.py | 실제 `ddk run`이 코드를 생성하고 visual check |

### 의도적으로 단순하게 유지하는 이유
- TypeScript strict mode 활성화 → tsc 에러 탐지 테스트 가능
- ESLint 설정 포함 → lint gate 테스트 가능
- 의존성 최소화 → pnpm install 속도 (CI 30초 이내 목표)
- Vite dev server 포함 → Playwright boot 테스트 가능
- React Hook 사용 (useState) → 코드 생성 시 Hook 규칙 위반 탐지 가능
