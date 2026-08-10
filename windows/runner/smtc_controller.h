// SMTC (System Media Transport Controls) integration for Windows.
// Registers the app with the OS media overlay (Win+K / volume OSD / media
// keys on keyboards) and bridges button events to the Flutter side.
#ifndef RUNNER_SMTC_CONTROLLER_H_
#define RUNNER_SMTC_CONTROLLER_H_

#include <windows.h>

#include <flutter/binary_messenger.h>
#include <flutter/encodable_value.h>
#include <flutter/method_channel.h>
#include <flutter/standard_method_codec.h>

#include <memory>
#include <string>

// Forward declaration avoids pulling WinRT types into the header.
struct SmtcControllerImpl;

class SmtcController {
 public:
  SmtcController(flutter::BinaryMessenger* messenger, HWND window);
  ~SmtcController();

  // Handles Dart -> native calls ("update" with a JSON map).
  void HandleMethodCall(
      const flutter::MethodCall<flutter::EncodableValue>& method_call,
      std::unique_ptr<flutter::MethodResult<flutter::EncodableValue>> result);

  // Called from the window message loop when a system media button is pressed.
  void HandleSystemMediaButton(int buttonCode);

 private:
  void ApplyUpdate(const flutter::EncodableMap& map);
  void SendButtonEvent(const std::string& event);

  HWND window_;
  std::string channel_name_;
  std::unique_ptr<flutter::MethodChannel<flutter::EncodableValue>> channel_;
  std::unique_ptr<SmtcControllerImpl> impl_;
};

#endif  // RUNNER_SMTC_CONTROLLER_H_