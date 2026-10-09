import axios from "axios";

const client = axios.create({
  baseURL: "/api",
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && error.config?.url !== "/auth/mode" && error.config?.url !== "/auth/login") {
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      // Under single sign-on there is no login page of ours: the proxy signs
      // people in. A 401 there means the forwarded identity token aged out, and
      // the proxy's own sign-in URL renews it (usually without a prompt).
      const proxyLogin = localStorage.getItem("proxy_login_url");
      if (localStorage.getItem("auth_mode") === "proxy" && proxyLogin) {
        window.location.href = proxyLogin;
      } else if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export default client;
