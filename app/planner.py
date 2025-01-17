import math

class StaffPlanner:
    def __init__(self, unit_census, vacation_days=30):
        # Constants
        self.unit_census = unit_census
        self.vacation_days = vacation_days
        self.year_days = 365
        self.weeks = 52
        self.day_hours = 24
        
        # Cost coefficients
        self.costs = {
            'sn': 1,
            'pn': 0.65,
            'hca': 0.4
        }
        
        # Calculate basic time metrics
        self.working_days = self.year_days - self.vacation_days
        self.working_weeks = self.working_days / 7
        self.hours_per_year = self.year_days * self.day_hours

        # Add shift hours for Model A
        self.model_a_shifts = {
            'early': 8,
            'late': 8,
            'night': 10
        }

    def calculate_yearly_hours(self, weekly_hours):
        return weekly_hours * self.working_weeks

    def calculate_staff_per_day(self, ratio, shifts):
        return math.ceil(self.unit_census / ratio * shifts)

    def calculate_yearly_staff_needs(self, staff_per_day, yearly_working_hours):
        hours_needed = staff_per_day * self.hours_per_year
        return math.ceil(hours_needed / yearly_working_hours)

    def calculate_overtime_cost_a(self, staff_per_day, yearly_hours, overtime_per_week, shift_type):
        shift_hours = self.model_a_shifts[shift_type]
        differential = 1.5
        
        # Calculate overtime hours for this shift
        total_ot_hours = overtime_per_week * self.weeks * shift_hours * staff_per_day
        
        # Calculate total hours needed for this number of staff
        total_hours_needed = staff_per_day * self.hours_per_year
        
        # Regular hours are total needed minus overtime
        regular_hours = total_hours_needed - total_ot_hours
        
        # Calculate hourly rate and costs
        hourly_rate = self.costs['sn'] / yearly_hours
        regular_staff_needed = regular_hours / yearly_hours
        regular_cost = regular_staff_needed * self.costs['sn']
        
        ot_cost = total_ot_hours * hourly_rate * differential
        
        return regular_cost + ot_cost

    def calculate_model_a(self, ratios=None, overtime_config=None):
        shifts = 3
        weekly_hours = 40
        ratios = ratios if ratios else {'sn': 8, 'pn': 12, 'hca': 16}
        
        yearly_hours = self.calculate_yearly_hours(weekly_hours)
        needs = {}
        costs = {}
        
        for staff_type, ratio in ratios.items():
            staff_per_day = self.calculate_staff_per_day(ratio, shifts)
            needs[staff_type] = self.calculate_yearly_staff_needs(staff_per_day, yearly_hours)
            
            if staff_type == 'sn' and overtime_config:
                total_ot_cost = 0
                staff_per_shift = staff_per_day // 3
                
                # Initialize total cost with regular hours cost
                total_reg_cost = needs[staff_type] * self.costs[staff_type]
                
                # Calculate overtime costs for each shift
                for shift_type, ot_hours in overtime_config.items():
                    if ot_hours > 0:
                        shift_ot_cost = self.calculate_overtime_cost_a(
                            staff_per_shift,
                            yearly_hours,
                            ot_hours,
                            shift_type
                        )
                        total_ot_cost += shift_ot_cost
                    
                # For shifts with zero overtime, use the regular cost proportion
                zero_ot_shifts = sum(1 for hours in overtime_config.values() if hours == 0)
                if zero_ot_shifts > 0:
                    regular_cost_per_shift = total_reg_cost / 3
                    total_ot_cost += regular_cost_per_shift * zero_ot_shifts
                
                costs[staff_type] = total_ot_cost
            else:
                costs[staff_type] = needs[staff_type] * self.costs[staff_type]
        
        return {
            'needs': needs,
            'costs': costs,
            'total_cost': sum(costs.values())
        }

    def calculate_overtime_cost(self, staff_per_day, yearly_hours, overtime_per_week):
        shift_hours = 12  # Model B uses 12-hour shifts
        differential = 1.5
        
        total_ot_hours = overtime_per_week * self.weeks * shift_hours
        total_hours_needed = staff_per_day * self.hours_per_year
        regular_hours = total_hours_needed - total_ot_hours
        
        hourly_rate = self.costs['sn'] / yearly_hours
        regular_staff_needed = regular_hours / yearly_hours
        regular_cost = regular_staff_needed * self.costs['sn']
        
        ot_cost = total_ot_hours * hourly_rate * differential
        
        return regular_cost + ot_cost

    def calculate_model_b(self, ratios=None, overtime_per_week=0):
        shifts = 2
        weekly_hours = 48
        ratios = ratios if ratios else {'sn': 3, 'hca': 16}
        
        yearly_hours = self.calculate_yearly_hours(weekly_hours)
        needs = {}
        costs = {}
        
        for staff_type, ratio in ratios.items():
            staff_per_day = self.calculate_staff_per_day(ratio, shifts)
            needs[staff_type] = self.calculate_yearly_staff_needs(staff_per_day, yearly_hours)
            
            if staff_type == 'sn' and overtime_per_week > 0:
                costs[staff_type] = self.calculate_overtime_cost(
                    staff_per_day,
                    yearly_hours,
                    overtime_per_week
                )
            else:
                costs[staff_type] = needs[staff_type] * self.costs[staff_type]
        
        return {
            'needs': needs,
            'costs': costs,
            'total_cost': sum(costs.values())
        }