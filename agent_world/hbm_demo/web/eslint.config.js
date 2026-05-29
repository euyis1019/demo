import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      // Feature 边界：跨 feature 只能从对方 index.ts 公共出口导入，
      // 禁止深引其 components/ hooks/ lib/ 内部文件（app → features → shared）。
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['../*/components/*', '../*/hooks/*', '../*/lib/*'],
              message:
                '跨 feature 请从该 feature 的 index.ts 公共出口导入，勿深引其内部文件。',
            },
          ],
        },
      ],
    },
  },
])
