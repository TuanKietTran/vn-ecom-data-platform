import "reflect-metadata";
import {
  Body,
  Controller,
  Get,
  HttpException,
  Module,
  Post,
  Query,
} from "@nestjs/common";
import type { NestExpressApplication } from "@nestjs/platform-express";
import { NestFactory } from "@nestjs/core";
import { chatRequest, dealRequest } from "@hunt/contracts";
const origin = new URL(process.env.PLATFORM_API_URL || "http://127.0.0.1:8201");
if (
  !["http:", "https:"].includes(origin.protocol) ||
  origin.username ||
  origin.password
)
  throw new Error(
    "PLATFORM_API_URL must be an http(s) URL without credentials",
  );
async function upstream(path: string, body?: unknown) {
  try {
    const response = await fetch(new URL(path, origin), {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(65000),
    });
    const data = await response.json();
    if (!response.ok)
      throw new HttpException(
        typeof data.detail === "string"
          ? data.detail
          : "The platform could not complete this request",
        response.status,
      );
    return data;
  } catch (error) {
    if (error instanceof HttpException) throw error;
    throw new HttpException(
      "The platform is unavailable. Please try again shortly.",
      503,
    );
  }
}
@Controller()
class ClientController {
  @Get("health") health() {
    return { status: "ok", service: "hunt-client-gateway" };
  }
  @Get("status") status() {
    return upstream("/chat/status");
  }
  @Get("upcoming") upcoming(
    @Query("include_synthetic") synthetic?: string,
    @Query("limit") limit?: string,
  ) {
    const parsedLimit = limit === undefined ? 20 : Number(limit);
    if (!Number.isInteger(parsedLimit) || parsedLimit < 1 || parsedLimit > 100)
      throw new HttpException("Limit must be an integer from 1 to 100.", 400);
    return upstream(
      "/deals/upcoming?" +
        new URLSearchParams({
          include_synthetic: synthetic === "true" ? "true" : "false",
          limit: String(parsedLimit),
        }),
    );
  }
  @Post("deals") deals(@Body() body: unknown) {
    const value = dealRequest.safeParse(body);
    if (!value.success)
      throw new HttpException(
        "Check your product, budget and eligibility fields.",
        400,
      );
    return upstream("/deals/search", value.data);
  }
  @Get("products") products(
    @Query("query") query: string,
    @Query("include_synthetic") demo?: string,
  ) {
    if (
      typeof query !== "string" ||
      query.trim().length < 2 ||
      query.length > 300
    )
      throw new HttpException(
        "Enter a product name between 2 and 300 characters.",
        400,
      );
    return upstream(
      "/products/search?" +
        new URLSearchParams({
          query,
          include_synthetic: demo === "true" ? "true" : "false",
        }),
    );
  }
  @Post("chat") chat(@Body() body: unknown, @Query("mode") mode?: string) {
    const value = chatRequest.safeParse(body);
    if (!value.success)
      throw new HttpException(
        "Keep messages under 8,000 characters and history under 20 turns.",
        400,
      );
    return upstream(mode === "model" ? "/chat" : "/chat/data", value.data);
  }
}
@Module({ controllers: [ClientController] })
class AppModule {}
async function bootstrap() {
  const app = await NestFactory.create<NestExpressApplication>(AppModule, {
    bodyParser: false,
  });
  app.useBodyParser("json", { limit: "1mb" });
  await app.listen(
    Number(process.env.GATEWAY_PORT || 3202),
    process.env.GATEWAY_HOST || "127.0.0.1",
  );
}
void bootstrap();
