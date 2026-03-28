import React from 'react';

interface AppProps {
  title?: string;
}

export default function App({ title = 'Hello' }: AppProps) {
  return <div className="p-4">{title}</div>;
}
