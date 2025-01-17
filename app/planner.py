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
        
        total_ot_hours = overtime_per_week * self.weeks * shift_hours
        total_hours_needed = staff_per_day * self.hours_per_year
        regular_hours = total_hours_needed - total_ot_hours
        
        hourly_rate = self.costs['sn'] / yearly_hours
        regular_staff_needed = regular_hours / yearly_hours
        regular_cost = regular_staff_needed * self.costs['sn']
        
        ot_cost = total_ot_hours * hourly_rate * differential
        
        return regular_cost + ot_cost

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

    def calculate_model_a(self, ratios=None, overtime_config=None):
        shifts = 3
        weekly_hours = 40
        # Use provided ratios or default to hardcoded values
        ratios = ratios if ratios else {'sn': 8, 'pn': 12, 'hca': 16}
    
        yearly_hours = self.calculate_yearly_hours(weekly_hours)
        needs = {}
        costs = {}
    
        for staff_type, ratio in ratios.items():
            staff_per_day = self.calculate_staff_per_day(ratio, shifts)
            needs[staff_type] = self.calculate_yearly_staff_needs(staff_per_day, yearly_hours)
        
            if staff_type == 'sn' and overtime_config:
                total_ot_cost = 0
                for shift_type, ot_hours in overtime_config.items():
                    if ot_hours > 0:
                        total_ot_cost += self.calculate_overtime_cost_a(
                            staff_per_day // 3,  # Divide by 3 as we have 3 shifts
                            yearly_hours,
                            ot_hours,
                            shift_type
                        )
                costs[staff_type] = total_ot_cost
            else:
                costs[staff_type] = needs[staff_type] * self.costs[staff_type]
    
        return {
            'needs': needs,
            'costs': costs,
            'total_cost': sum(costs.values())
        }

    def calculate_model_b(self, ratios=None, overtime_per_week=0):
        shifts = 2
        weekly_hours = 48
        # Use provided ratios or default to hardcoded values
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

# Usage example
if __name__ == "__main__":
    planner = StaffPlanner(unit_census=32)
    
    # Calculate Model A results with overtime
    overtime_config_a = {
        'early': 1,  # 2 overtime shifts per week in early shift
        'late': 1,    # 1 overtime shifts per week in late shift
        'night': 1   # 1 overtime shift per week in night shift
    }
    
    model_a = planner.calculate_model_a(overtime_config=overtime_config_a)
    print("\nModel A Results (with overtime):")
    print(f"Staff Needs: {model_a['needs']}")
    print(f"Costs: {model_a['costs']}")
    print(f"Total Cost: {model_a['total_cost']}")
    
    # Calculate Model B results with overtime
    model_b = planner.calculate_model_b(overtime_per_week=5)
    print("\nModel B Results (with overtime):")
    print(f"Staff Needs: {model_b['needs']}")
    print(f"Costs: {model_b['costs']}")
    print(f"Total Cost: {model_b['total_cost']}")