#include "smtc_controller.h"

#include <flutter/standard_method_codec.h>

#include <algorithm>
#include <array>
#include <cwchar>
#include <string>

// --- C++/WinRT (SMTC) implementation ------------------------------------

#include <winrt/base.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Media.h>
#include <winrt/Windows.Storage.Streams.h>

namespace winrt {
using namespace winrt::Windows::Media;
using winrt::Windows::Storage::Streams::RandomAccessStreamReference;
}

// ISystemMediaTransportControlsInterop lets desktop (non-UWP) apps obtain
// an SMTC instance bound to a window handle.
struct __declspec(uuid("ddb04759-cc74-4d5e-b6de-4b3c90d5bed6"))
    ISystemMediaTransportControlsInterop : public IUnknown {
  virtual HRESULT STDMETHODCALLTYPE GetForWindow(
      HWND appWindow, REFIID riid, void** mediaTransportControl) = 0;
};

struct SmtcControllerImpl {
  winrt::SystemMediaTransportControls smtc = nullptr;
  winrt::event_token buttonToken{};
};

// Button codes posted from the SMTC event thread to the UI thread.
enum {
  kMediaButtonPlayPause = 1,
  kMediaButtonNext = 2,
  kMediaButtonPrevious = 3,
  kMediaButtonStop = 4,
};

SmtcController::SmtcController(flutter::BinaryMessenger* messenger, HWND window)
    : window_(window),
      channel_name_("playlist_admin/smtc"),
      impl_(std::make_unique<SmtcControllerImpl>()) {
  channel_ = std::make_unique<flutter::MethodChannel<flutter::EncodableValue>>(
      messenger, channel_name_, &flutter::StandardMethodCodec::GetInstance());
  channel_->SetMethodCallHandler(std::bind(
      &SmtcController::HandleMethodCall, this, std::placeholders::_1,
      std::placeholders::_2));

  // Create an SMTC instance bound to our top-level window.
  try {
    auto interop =
        winrt::get_activation_factory<winrt::SystemMediaTransportControls,
                                      ISystemMediaTransportControlsInterop>();
    winrt::SystemMediaTransportControls smtc{nullptr};
    HRESULT hr = interop->GetForWindow(
        window_, winrt::guid_of<winrt::SystemMediaTransportControls>(),
        winrt::put_abi(smtc));
    if (FAILED(hr)) {
      return;
    }
    impl_->smtc = smtc;

    impl_->smtc.IsEnabled(true);
    impl_->smtc.IsPlayEnabled(true);
    impl_->smtc.IsPauseEnabled(true);
    impl_->smtc.IsNextEnabled(true);
    impl_->smtc.IsPreviousEnabled(true);
    impl_->smtc.IsStopEnabled(true);
    impl_->smtc.PlaybackStatus(winrt::MediaPlaybackStatus::Closed);

    // Button events arrive on the SMTC thread; marshal to the UI thread via
    // a WM_APP message so the Flutter channel is only touched on the platform
    // thread.
    impl_->buttonToken = impl_->smtc.ButtonPressed(
        [this](winrt::SystemMediaTransportControls const&,
               winrt::SystemMediaTransportControlsButtonPressedEventArgs const& args) {
          int code = 0;
          switch (args.Button()) {
            case winrt::SystemMediaTransportControlsButton::Play:
            case winrt::SystemMediaTransportControlsButton::Pause:
              code = kMediaButtonPlayPause;
              break;
            case winrt::SystemMediaTransportControlsButton::Next:
              code = kMediaButtonNext;
              break;
            case winrt::SystemMediaTransportControlsButton::Previous:
              code = kMediaButtonPrevious;
              break;
            case winrt::SystemMediaTransportControlsButton::Stop:
              code = kMediaButtonStop;
              break;
            default:
              return;
          }
          ::PostMessageW(window_, WM_APP, code, 0);
        });
  } catch (...) {
  }
}

SmtcController::~SmtcController() {
  if (impl_->smtc) {
    try {
      impl_->smtc.ButtonPressed(impl_->buttonToken);
      impl_->smtc.IsEnabled(false);
      impl_->smtc = nullptr;
    } catch (...) {
    }
  }
}

void SmtcController::HandleSystemMediaButton(int buttonCode) {
  SendButtonEvent([&]() -> std::string {
    switch (buttonCode) {
      case kMediaButtonPlayPause:
        return "play_pause";
      case kMediaButtonNext:
        return "next";
      case kMediaButtonPrevious:
        return "previous";
      case kMediaButtonStop:
        return "stop";
      default:
        return "";
    }
  }());
}

void SmtcController::SendButtonEvent(const std::string& event) {
  if (event.empty()) {
    return;
  }
  flutter::EncodableValue value(event);
  channel_->InvokeMethod("onButton", std::make_unique<flutter::EncodableValue>(value));
}

void SmtcController::HandleMethodCall(
    const flutter::MethodCall<flutter::EncodableValue>& method_call,
    std::unique_ptr<flutter::MethodResult<flutter::EncodableValue>> result) {
  if (method_call.method_name() == "update") {
    const auto* args = std::get_if<flutter::EncodableMap>(method_call.arguments());
    if (args != nullptr) {
      ApplyUpdate(*args);
    }
    result->Success();
    return;
  }
  result->NotImplemented();
}

void SmtcController::ApplyUpdate(const flutter::EncodableMap& map) {
  try {
    if (!impl_->smtc) {
      return;
    }
    auto getStr = [&map](const char* key) -> std::wstring {
      auto it = map.find(flutter::EncodableValue(key));
      if (it == map.end()) {
        return std::wstring();
      }
      const auto* s = std::get_if<std::string>(&it->second);
      if (s == nullptr) {
        return std::wstring();
      }
      return std::wstring(s->begin(), s->end());
    };
    auto getBool = [&map](const char* key, bool def) -> bool {
      auto it = map.find(flutter::EncodableValue(key));
      if (it == map.end()) {
        return def;
      }
      const auto* b = std::get_if<bool>(&it->second);
      return b != nullptr ? *b : def;
    };

    const std::wstring title = getStr("title");
    const std::wstring artist = getStr("artist");
    const std::wstring album = getStr("album");
    const std::wstring artworkUrl = getStr("artworkUrl");
    const bool playing = getBool("playing", false);

    auto updater = impl_->smtc.DisplayUpdater();
    updater.Type(winrt::MediaPlaybackType::Music);
    if (!title.empty()) {
      updater.MusicProperties().Title(winrt::hstring(title));
    }
    if (!artist.empty()) {
      updater.MusicProperties().Artist(winrt::hstring(artist));
    }
    if (!album.empty()) {
      updater.MusicProperties().AlbumTitle(winrt::hstring(album));
    }
    if (!artworkUrl.empty()) {
      try {
        auto ref = winrt::RandomAccessStreamReference::CreateFromUri(
            winrt::Windows::Foundation::Uri(winrt::hstring(artworkUrl)));
        updater.Thumbnail(ref);
      } catch (...) {
      }
    }
    updater.Update();

    impl_->smtc.PlaybackStatus(
        playing ? winrt::MediaPlaybackStatus::Playing
                : winrt::MediaPlaybackStatus::Paused);
  } catch (...) {
  }
}