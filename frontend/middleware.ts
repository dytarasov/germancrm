import { NextRequest, NextResponse } from "next/server";

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (pathname.startsWith("/login")) return NextResponse.next();
  if (!req.cookies.get("crm_session")) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // Последняя группа исключает файлы статики (всё с расширением: logo.png,
  // icon.png, apple-icon.png и т.п.) — иначе логотип на странице логина
  // редиректится на /login и не загружается.
  matcher: ["/((?!api|healthz|_next/static|_next/image|favicon.ico|.*\\..*).*)"],
};
