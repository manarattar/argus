/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  eslint: { dirs: ['src'] },
  // The repository may live on a filesystem without symlink support (exFAT on
  // Windows, for instance), where webpack's readlink probe throws EISDIR.
  // Nothing in this project relies on symlinked modules, so resolving them is
  // pure cost.
  webpack: (config) => {
    config.resolve.symlinks = false;
    config.cache = false;
    return config;
  },
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'Referrer-Policy', value: 'no-referrer' },
          { key: 'Permissions-Policy', value: 'geolocation=(), microphone=(), camera=()' },
        ],
      },
    ];
  },
};

export default nextConfig;
