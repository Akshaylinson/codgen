import './globals.css';

export const metadata = {
  title: 'Codgen — AI Image & Video Studio',
  description: 'Generate AI images and videos using 200+ models — Flux, Midjourney, Kling, Veo, Seedance and more. Powered by Codgen.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
