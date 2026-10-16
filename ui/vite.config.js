import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({plugins:[react()], server:{proxy:Object.fromEntries(['/ask','/me','/tool','/catalogue','/health','/pending','/approve','/feedback','/names','/export'].map(p=>[p,'http://127.0.0.1:8000']))},build:{sourcemap:false}});
