import { useEffect } from "react";
import { Route, Routes, useLocation } from "react-router";
import ChatWidget from "./components/ChatWidget.tsx";
import Header from "./components/Header.tsx";
import AboutPage from "./pages/AboutPage.tsx";
import HomePage from "./pages/HomePage.tsx";
import LoginPage from "./pages/LoginPage.tsx";
import NotFoundPage from "./pages/NotFoundPage.tsx";
import ProductDetailPage from "./pages/ProductDetailPage.tsx";
import ProductsPage from "./pages/ProductsPage.tsx";
import SignupPage from "./pages/SignupPage.tsx";

function ScrollToTop() {
  const { pathname } = useLocation();
  // Block body: newer browsers return a Promise from scrollTo, which React rejects as an effect cleanup.
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

export default function App() {
  return (
    <>
      <ScrollToTop />
      <Header />
      <main className="page">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/products" element={<ProductsPage />} />
          <Route path="/products/:productId" element={<ProductDetailPage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </main>
      <footer className="site-footer">
        <span>© {new Date().getFullYear()} Campus Customs</span>
        <span className="muted">Yale apparel for students, alumni and families.</span>
      </footer>
      <ChatWidget />
    </>
  );
}
