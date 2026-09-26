import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir:'./tests/e2e', fullyParallel:false, workers:1, timeout:30000,
  use:{baseURL:'http://127.0.0.1:15173',headless:true,channel:'msedge',viewport:{width:1440,height:900},trace:'retain-on-failure'},
  webServer:{command:'node scripts/dev.mjs',url:'http://127.0.0.1:15173',reuseExistingServer:false,timeout:60000,
    env:{STONIC_PORT:'18765',STONIC_UI_PORT:'15173',STONIC_DATA_DIR:'.runtime/e2e-data'}},
});
