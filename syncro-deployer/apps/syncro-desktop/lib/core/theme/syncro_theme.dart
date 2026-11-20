import 'package:flutter/material.dart';

/// Swiss-Industrial Desktop Palette for Syncro Desktop (high contrast, zero cliché neon/purple).
class SyncroTheme {
  static const Color canvas = Color(0xFF10141A);
  static const Color surface = Color(0xFF161C24);
  static const Color surfaceElevated = Color(0xFF1D2530);
  static const Color well = Color(0xFF0C1015);
  static const Color hairline = Color(0xFF283240);

  static const Color textPrimary = Color(0xFFECF1F7);
  static const Color textSecondary = Color(0xFFA2B0C2);
  static const Color textMuted = Color(0xFF6C7C90);

  static const Color accentSteel = Color(0xFF25A8BA);
  static const Color statusOk = Color(0xFF2FB377);
  static const Color statusWarn = Color(0xFFE9A22E);
  static const Color statusDanger = Color(0xFFE04F44);

  static ThemeData buildDarkTheme() {
    final base = ThemeData.dark(useMaterial3: true);
    return base.copyWith(
      scaffoldBackgroundColor: canvas,
      colorScheme: const ColorScheme.dark(
        primary: accentSteel,
        secondary: statusOk,
        surface: surface,
        error: statusDanger,
        onPrimary: Color(0xFF071216),
        onSurface: textPrimary,
      ),
      cardTheme: CardTheme(
        color: surface,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8),
          side: const BorderSide(color: hairline),
        ),
        margin: EdgeInsets.zero,
      ),
      dividerColor: hairline,
      textTheme: base.textTheme.apply(
        bodyColor: textPrimary,
        displayColor: textPrimary,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: well,
        isDense: true,
        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(6),
          borderSide: const BorderSide(color: hairline),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(6),
          borderSide: const BorderSide(color: hairline),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(6),
          borderSide: const BorderSide(color: accentSteel),
        ),
      ),
    );
  }
}
