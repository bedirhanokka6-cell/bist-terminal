import './globals.css';
export const metadata = { title: 'BIST Terminal Pro', description: 'BIST analiz terminali' };
export default function RootLayout({children}:{children:React.ReactNode}){
  return <html lang="tr"><body>{children}</body></html>;
}
