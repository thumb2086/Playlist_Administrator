import 'package:flutter/material.dart';

class AppColors {
  // Dark theme colors
  static const bg = Color(0xFF0D0D0D);
  static const surface = Color(0xFF1A1A1A);
  static const surfaceLight = Color(0xFF242424);
  static const card = Color(0xFF1E1E1E);
  static const cardHover = Color(0xFF2A2A2A);
  static const border = Color(0xFF2E2E2E);
  static const borderLight = Color(0xFF3A3A3A);
  static const accent = Color(0xFF1DB954);
  static const accentHover = Color(0xFF1ED760);
  static Color get accentDim => const Color(0xFF1DB954).withValues(alpha: 0.15);
  static const text = Color(0xFFFFFFFF);
  static const textSecondary = Color(0xFFB3B3B3);
  static const textMuted = Color(0xFF6A6A6A);
  static const error = Color(0xFFE22134);
  static const warning = Color(0xFFF59B23);
  static const success = Color(0xFF1DB954);

  // Light theme colors
  static const bgLight = Color(0xFFF5F5F5);
  static const surfaceLightBg = Color(0xFFFFFFFF);
  static const cardLight = Color(0xFFFFFFFF);
  static const borderLightBg = Color(0xFFE0E0E0);
  static const textLight = Color(0xFF212121);
  static const textSecondaryLight = Color(0xFF616161);
  static const textMutedLight = Color(0xFF9E9E9E);
  static const surfaceElementLight = Color(0xFFEEEEEE);
}

ThemeData buildDarkTheme() {
  return ThemeData(
    brightness: Brightness.dark,
    scaffoldBackgroundColor: AppColors.bg,
    primaryColor: AppColors.accent,
    colorScheme: const ColorScheme.dark(
      primary: AppColors.accent,
      secondary: AppColors.accent,
      surface: AppColors.surface,
      error: AppColors.error,
    ),
    fontFamily: 'Segoe UI',
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.bg,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: TextStyle(
        color: AppColors.text,
        fontSize: 20,
        fontWeight: FontWeight.w600,
        letterSpacing: -0.3,
      ),
    ),
    cardTheme: CardThemeData(
      color: AppColors.card,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: const BorderSide(color: AppColors.border, width: 1),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.surfaceLight,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: AppColors.border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: AppColors.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: AppColors.accent, width: 1.5),
      ),
      hintStyle: const TextStyle(color: AppColors.textMuted, fontSize: 13),
      labelStyle: const TextStyle(color: AppColors.textSecondary, fontSize: 13),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: AppColors.accent,
        foregroundColor: Colors.black,
        disabledBackgroundColor: AppColors.surfaceLight,
        disabledForegroundColor: AppColors.textMuted,
        elevation: 0,
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        textStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: AppColors.accent,
      ),
    ),
    dividerTheme: const DividerThemeData(
      color: AppColors.border,
      thickness: 1,
    ),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: AppColors.surfaceLight,
      contentTextStyle: const TextStyle(color: AppColors.text),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      behavior: SnackBarBehavior.floating,
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: AppColors.accent,
      linearTrackColor: AppColors.border,
    ),
    textTheme: const TextTheme(
      headlineLarge: TextStyle(color: AppColors.text, fontSize: 28, fontWeight: FontWeight.bold, letterSpacing: -0.5),
      headlineMedium: TextStyle(color: AppColors.text, fontSize: 22, fontWeight: FontWeight.w600),
      titleLarge: TextStyle(color: AppColors.text, fontSize: 18, fontWeight: FontWeight.w600),
      titleMedium: TextStyle(color: AppColors.text, fontSize: 15, fontWeight: FontWeight.w500),
      bodyLarge: TextStyle(color: AppColors.text, fontSize: 14),
      bodyMedium: TextStyle(color: AppColors.textSecondary, fontSize: 13),
      bodySmall: TextStyle(color: AppColors.textMuted, fontSize: 12),
      labelMedium: TextStyle(color: AppColors.textSecondary, fontSize: 12, fontWeight: FontWeight.w500),
    ),
  );
}

ThemeData buildLightTheme() {
  return ThemeData(
    brightness: Brightness.light,
    scaffoldBackgroundColor: AppColors.bgLight,
    primaryColor: AppColors.accent,
    colorScheme: const ColorScheme.light(
      primary: AppColors.accent,
      secondary: AppColors.accent,
      surface: AppColors.surfaceLightBg,
      error: AppColors.error,
    ),
    fontFamily: 'Segoe UI',
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.bgLight,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: TextStyle(
        color: AppColors.textLight,
        fontSize: 20,
        fontWeight: FontWeight.w600,
        letterSpacing: -0.3,
      ),
    ),
    cardTheme: CardThemeData(
      color: AppColors.cardLight,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: const BorderSide(color: AppColors.borderLightBg, width: 1),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.surfaceElementLight,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: AppColors.borderLightBg),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: AppColors.borderLightBg),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: AppColors.accent, width: 1.5),
      ),
      hintStyle: const TextStyle(color: AppColors.textMutedLight, fontSize: 13),
      labelStyle: const TextStyle(color: AppColors.textSecondaryLight, fontSize: 13),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: AppColors.accent,
        foregroundColor: Colors.white,
        disabledBackgroundColor: AppColors.surfaceElementLight,
        disabledForegroundColor: AppColors.textMutedLight,
        elevation: 0,
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        textStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: AppColors.accent,
      ),
    ),
    dividerTheme: const DividerThemeData(
      color: AppColors.borderLightBg,
      thickness: 1,
    ),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: AppColors.surfaceElementLight,
      contentTextStyle: const TextStyle(color: AppColors.textLight),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      behavior: SnackBarBehavior.floating,
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: AppColors.accent,
      linearTrackColor: AppColors.borderLightBg,
    ),
    textTheme: const TextTheme(
      headlineLarge: TextStyle(color: AppColors.textLight, fontSize: 28, fontWeight: FontWeight.bold, letterSpacing: -0.5),
      headlineMedium: TextStyle(color: AppColors.textLight, fontSize: 22, fontWeight: FontWeight.w600),
      titleLarge: TextStyle(color: AppColors.textLight, fontSize: 18, fontWeight: FontWeight.w600),
      titleMedium: TextStyle(color: AppColors.textLight, fontSize: 15, fontWeight: FontWeight.w500),
      bodyLarge: TextStyle(color: AppColors.textLight, fontSize: 14),
      bodyMedium: TextStyle(color: AppColors.textSecondaryLight, fontSize: 13),
      bodySmall: TextStyle(color: AppColors.textMutedLight, fontSize: 12),
      labelMedium: TextStyle(color: AppColors.textSecondaryLight, fontSize: 12, fontWeight: FontWeight.w500),
    ),
  );
}
