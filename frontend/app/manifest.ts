import type { MetadataRoute } from 'next';

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'BIST Terminal',
    short_name: 'BIST Terminal',
    description: 'BIST 30 teknik analiz, sinyal ve bildirim terminali.',
    start_url: '/',
    display: 'standalone',
    background_color: '#091826',
    theme_color: '#0f304a',
    orientation: 'portrait-primary',
    icons: [
      {
        src: '/icon-192.png',
        sizes: '192x192',
        type: 'image/png',
        purpose: 'any',
      },
      {
        src: '/icon-512.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'any',
      },
    ],
  };
}
