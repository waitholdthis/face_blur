/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Allow images served from the API's signed-URL asset endpoint.
  images: { unoptimized: true },
};

export default nextConfig;
