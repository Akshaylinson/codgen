/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ['studio'],
  output: 'standalone',   // required for Docker multi-stage build
};

export default nextConfig;
