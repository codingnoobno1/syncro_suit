import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:syncro_desktop/main.dart';
import 'package:syncro_desktop/state/syncro_controller.dart';

void main() {
  testWidgets('SyncroDesktopApp renders 7-module Suite rail and switches Agentic/Manual mode',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final ctrl = SyncroController(startBackgroundTimers: false);
    addTearDown(ctrl.dispose);

    await tester.pumpWidget(
      SyncroDesktopApp(controller: ctrl, autoBootstrap: false),
    );
    await tester.pumpAndSettle();

    expect(find.text('SYNCRO SUITE'), findsOneWidget);
    expect(find.text('Syncro Desktop'), findsOneWidget);
    expect(find.text('Syncro Deployer'), findsOneWidget);
    expect(find.text('Syncro Tester'), findsOneWidget);
    expect(find.text('AGENTIC MODE'), findsOneWidget);
    expect(find.text('MANUAL DEVOPS MODE'), findsOneWidget);
    expect(find.textContaining('AGENTIC AUTOPILOT'), findsOneWidget);

    await tester.tap(find.text('MANUAL DEVOPS MODE'));
    await tester.pumpAndSettle();

    expect(find.textContaining('MANUAL DEVOPS MODE · EXPLICIT STAGE-GATE'), findsOneWidget);
  });
}
