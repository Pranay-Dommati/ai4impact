from django.db import models


class Location(models.Model):
	LEVEL_CHOICES = [
		("city", "City"),
		("village", "Village"),
	]

	city = models.CharField(max_length=100)
	area = models.CharField(max_length=100)
	level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default="city")

	class Meta:
		unique_together = ("city", "area")
		ordering = ["city", "area"]

	def __str__(self):
		return f"{self.city} - {self.area}"


class Department(models.Model):
	name = models.CharField(max_length=100)
	category = models.CharField(max_length=50)

	class Meta:
		ordering = ["name"]

	def __str__(self):
		return f"{self.name} ({self.category})"


class DepartmentAssignment(models.Model):
	department = models.ForeignKey(Department, on_delete=models.CASCADE)
	location = models.ForeignKey(Location, on_delete=models.CASCADE)

	class Meta:
		unique_together = ("department", "location")

	def __str__(self):
		return f"{self.location} -> {self.department}"


class Officer(models.Model):
	name = models.CharField(max_length=120)
	username = models.CharField(max_length=60, unique=True)
	password = models.CharField(max_length=120)
	department = models.ForeignKey(Department, on_delete=models.CASCADE)
	location_ref = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True)
	is_active = models.BooleanField(default=True)
	is_manager = models.BooleanField(default=False)
	max_active_tasks = models.IntegerField(default=2)
	current_load = models.IntegerField(default=0)

	class Meta:
		ordering = ["department__name", "current_load", "name"]

	def __str__(self):
		return f"{self.name} ({self.department.name})"


class Complaint(models.Model):
	CATEGORY_CHOICES = [
		("water", "Water"),
		("electricity", "Electricity"),
		("roads", "Roads"),
		("sanitation", "Sanitation"),
		("other", "Other"),
	]

	SOURCE_CHOICES = [
		("portal", "Portal"),
		("telegram", "Telegram"),
	]

	PRIORITY_CHOICES = [
		("low", "Low"),
		("medium", "Medium"),
		("high", "High"),
	]

	STATUS_CHOICES = [
		("pending", "Pending"),
		("resolved", "Resolved"),
	]

	text = models.TextField()
	category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
	location = models.CharField(max_length=120)
	source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
	priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="low")
	score = models.IntegerField(default=0)
	impact_score = models.IntegerField(default=0)
	severity = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="low")
	urgency = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="low")
	risk_type = models.CharField(max_length=80, blank=True)
	affected_population_estimate = models.IntegerField(default=0)
	duration_hint = models.CharField(max_length=80, blank=True)
	issue_type = models.CharField(max_length=100, blank=True)
	cluster_id = models.CharField(max_length=120, blank=True)
	ai_confidence = models.FloatField(default=0)
	ai_analysis = models.JSONField(default=dict, blank=True)
	citizen_chat_id = models.BigIntegerField(null=True, blank=True)
	location_ref = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True)
	assigned_department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
	status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]

	def __str__(self):
		return f"{self.category} complaint at {self.location} ({self.priority})"


class ResolutionTask(models.Model):
	STATE_CHOICES = [
		("queued", "Queued"),
		("assigned", "Assigned"),
		("in_progress", "In Progress"),
		("resolved_pending_verification", "Resolved Pending Verification"),
		("closed", "Closed"),
		("escalated", "Escalated"),
	]

	VERIFICATION_CHOICES = [
		("not_requested", "Not Requested"),
		("pending", "Pending"),
		("approved", "Approved"),
		("rejected", "Rejected"),
	]

	complaint = models.OneToOneField(Complaint, on_delete=models.CASCADE, related_name="resolution_task")
	officer = models.ForeignKey(Officer, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks")
	manager = models.ForeignKey(Officer, on_delete=models.SET_NULL, null=True, blank=True, related_name="managed_tasks")
	state = models.CharField(max_length=40, choices=STATE_CHOICES, default="assigned")
	sla_due_at = models.DateTimeField()
	assigned_at = models.DateTimeField(auto_now_add=True)
	resolved_at = models.DateTimeField(null=True, blank=True)
	closed_at = models.DateTimeField(null=True, blank=True)
	ttr_minutes = models.IntegerField(default=0)
	escalated_count = models.IntegerField(default=0)
	last_escalated_at = models.DateTimeField(null=True, blank=True)
	escalated_to_manager_at = models.DateTimeField(null=True, blank=True)
	verification_status = models.CharField(max_length=20, choices=VERIFICATION_CHOICES, default="not_requested")
	verification_requested_at = models.DateTimeField(null=True, blank=True)
	verification_photo_url = models.URLField(blank=True)
	verified_at = models.DateTimeField(null=True, blank=True)
	notes = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]

	def __str__(self):
		return f"Task #{self.id} {self.complaint_id} {self.state}"
