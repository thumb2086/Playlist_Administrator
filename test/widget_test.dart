import 'package:flutter_test/flutter_test.dart';
import 'package:playlist_admin/app.dart';

void main() {
  testWidgets('App should build', (WidgetTester tester) async {
    await tester.pumpWidget(const PlaylistAdminApp());
    expect(find.text('Playlist Admin'), findsOneWidget);
  });
}
