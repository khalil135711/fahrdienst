class Ride {
  final int id;
  final String status; // requested, accepted, arriving, in_progress, completed, cancelled
  final String? driverName;
  final double? driverRating;
  final String? vehicle;
  final int? etaMinutes;

  Ride({
    required this.id,
    required this.status,
    this.driverName,
    this.driverRating,
    this.vehicle,
    this.etaMinutes,
  });

  factory Ride.fromJson(Map<String, dynamic> j) => Ride(
        id: j['id'],
        status: j['status'],
        driverName: j['driver_name'],
        driverRating: (j['driver_rating'] as num?)?.toDouble(),
        vehicle: j['vehicle'],
        etaMinutes: j['eta_minutes'],
      );
}
